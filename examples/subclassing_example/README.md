## Custom image manipulation in `pdfplumber`
The AbstractImageHandler class serves as an interface defining minimum required functionality 
for user made *ImageHandler class objects.

For the clearest example of how to create a custom subclass from AbstractImageHandler, see `pdfplumber.display.PILImageHandler`.

In order to implement a customized subclass of AbstractImageHandler, the programmer needs to follow these guiding concepts:

1. pdfplumber encapsulates image handling code inside of *ImageHandler objects. 
    * The primary intention of this encapsulation is to allow programmerss to leverage image manipulation libraries like
      opencv to extend the functionality of pdfplumber through a well defined interface.  
2. The required input/output of each function in the class is based upon the requirements defined by the functionality 
   of the `PIL.Image.Image` class and the `PIL.ImageDraw.ImageDraw` classes; as they were the tools previously used by
   pdfplumber for image manipulation.
3. The custom subclass needs to be "registered" as an image handler by adding its class reference to the 
   `pdfplumber.display.image_handler_types` dict.
    * For clarifying instructions on how to how you should add your custom handler to the types dict see the brief code 
      example bellow.
4. The programmer must also create a subclass of the `pdfplumber.display.BasePageImage` associated with their custom
   *ImageHandler class. This custom PageImage class will use the image_handler_types dict to screen parameter inputs
   and ensure custom interface requirements will be met.
   
#### subclass example
```python
from pdfplumber.display import BasePageImage,AbstractImageHandler
from pdfplumber.display import image_handler_types
from pdfplumber.display import DEFAULT_RESOLUTION
from pdfplumber.display import get_page_image
from io import BytesIO
from pdfplumber.page import Page
import cv2
import numpy as np
import pathlib as pl


class CV2ImageHandlerExample(AbstractImageHandler):

    @property
    def original_image(self):
        return self._original

    @property
    def annotated_image(self):
        if self._annotated is None:
            if self._original is not None:
                self._annotated = self._original.copy()
        return self._annotated

    @original_image.setter
    def original_image(self, path_page_or_array):
        if isinstance(path_page_or_array, (str,pl.Path)):
            self._original = cv2.imread(path_page_or_array)
        elif isinstance(path_page_or_array,Page):
            # we need to imitate the `get_page_image` function from `pdfplumber.display`, adapting to opencv equivalent
            # functionality where possible.
            self._stream = path_page_or_array.pdf.stream
            self._page_no = path_page_or_array.page_number
            self._original = np.array(get_page_image(self.stream,self.page_number,self.resolution))
        elif isinstance(path_page_or_array,np.ndarray):
            self._original = path_page_or_array
        else:
            raise ValueError("path_or_array was passed an object that wasn't a valid path string, pdfplumber Page, nor numpy ndarray.")
        # Because we've changed the original image, we should make sure the
        # annotated image reflects this.
        #       Note: a more advanced implementation might backup the annotated image somehow,
        #             or implement a method for remembering the steps to reapply all annotations done
        #             so far but with the new original image.
        self.reset()

    @annotated_image.setter
    def annotated_image(self,path_page_or_array):
        # Note:
        #   a more advanced implementation might backup the annotated image before overwriting it.
        # Also note:
        #   Possible problem here, as we change the annotated image, but have no means to assure that
        #   this change is in any way related to our current reference to the original.
        if isinstance(path_page_or_array, (str,pl.Path)):
            self._annotated = cv2.imread(path_page_or_array)
        elif isinstance(path_page_or_array,Page):
            # we need to imitate the `get_page_image` function from `pdfplumber.display`, adapting to opencv equivalent
            # functionality where possible.
            self._stream = path_page_or_array.pdf.stream
            self._page_no = path_page_or_array.page_number
            self._annotated = np.array(get_page_image(self.stream,self.page_number,self.resolution))
        else:
            raise ValueError("path_or_array was passed an object that wasn't a valid path string, pdfplumber Page, nor numpy ndarray.")

    def save(self, fp, format=None, **params):
        data_to_save = params.pop("data_to_save",self._annotated) # type: np.ndarray
        # a proper implementation of this CV2ImageHandlerExample would also include
        # sanity checks that filename is correctly formatted, has a valid file typing extension,
        # and that the data_to_save has an appropriate numpy dtype for that extension.
        if isinstance(fp,pl.Path):
            fp = str(fp.resolve())
        if isinstance(fp,str):
            # save img to disk using fp as a path string
            cv2.imwrite(fp, data_to_save)
        elif isinstance(fp,BytesIO):
            format = format if format is not None else "PNG"
            good,byte_arr = cv2.imencode(format,data_to_save)
            fp.write(byte_arr)
        else:
            raise ValueError("CV2ImageHandlerExample.save(fp,format,**params) was given an unrecognized object for the `fp` parameter."
                             f"\n\ttype(fp): {type(fp)}")

    def reset(self, mode=None, **kwargs):
        """In this implementation, we are taking the image mode and using it as we would a numpy.dtype"""
        if mode is None:
            mode = self._annotated.dtype
        elif isinstance(mode,str):
            if "rgb" == mode.lower():
                mode = np.uint8
            elif "rgba" == mode.lower():
                mode = np.float32
        self.annotated_image = self._original.astype(mode)

    def size(self, **kwargs):
        # This naive implementation assumes that the original image is a single image.
        # Where the 0'th dimension is height, and the 1'st dimension is width
        return self.original_image.shape[1:0:-1]

    def crop_original(self, cropbox, **kwargs):
        # The order of points in the cropbox parameter needs to be double checked, but if we assume
        # that cropbox[0] is the top left corner of the box, and cropbox[1:4] proceeds in clockwise
        # order through the box vertices, then the following is an appropriate, if not over-simple,
        # implementation.
        # Also assume that each point is a 2-tuple expressing coordinate data in the form of (x,y).
        top = cropbox[0][1]
        bottom = cropbox[3][1]
        left = cropbox[0][0]
        right = cropbox[1][0]
        # again, this is implementation assumes we aren't working with a stack of images, and that the 0'th
        # axis is the height of the image, and the 1'st axis is the width.
        self._original = self._original[top:bottom,left:right]
        self._annotated = self._annotated[top:bottom,left:right]


    def line(self, points, color, width, **kwargs):
        if len(points)==2:
            x1,y1 = points[0]
            x2,y2 = points[1]
        else:
            x1,y1,x2,y2 = points
        thickness = kwargs.get("thickness",width)
        lineType = kwargs.get("lineType",None)
        shift = kwargs.get("shift",None)
        cv2.line(self._annotated,(x1,y1),(x2,y2),color,thickness,lineType,shift)

    def rectangle(self, bbox, color, outline_color, **kwargs):
        if len(bbox)==2:
            x1,y1 = bbox[0]
            x2,y2 = bbox[1]
        else:
            x1,y1,x2,y2 = bbox
        thickness = kwargs.get("thickness",1)
        lineType = kwargs.get("lineType",None)
        shift = kwargs.get("shift",None)
        cv2.rectangle(self._annotated,(x1,y1),(x2,y2),color,thickness,lineType,shift)

    def ellipse(self, bbox, color, stroke, **kwargs):
        if len(bbox)==2:
            x1,y1 = bbox[0]
            x2,y2 = bbox[1]
        else:
            x1,y1,x2,y2 = bbox
        axis_len = x2-x1,y2-y1
        center = axis_len[0]//2,axis_len[1]//2
        thickness = kwargs.get("thickness",1)
        lineType = kwargs.get("lineType",None)
        shift = kwargs.get("shift",None)
        cv2.ellipse(self._annotated,center,axis_len,0,360,color,thickness,lineType,shift)


image_handler_types["CV2"] = CV2ImageHandlerExample


class CV2PageImage(BasePageImage):
    def __init__(self, page, original: AbstractImageHandler = None, resolution=None,
                 image_handler_type: str or CV2ImageHandlerExample=CV2ImageHandlerExample):
        resolution = resolution if resolution is not None else DEFAULT_RESOLUTION
        image_handler_type = image_handler_types.get(image_handler_type,CV2ImageHandlerExample)
        super().__init__(page, original, resolution, image_handler_type)
```

#### Example of how to use a custom subclass
```python
import pathlib as pl
from typing import List
from examples.subclassing_example.cv2_page_image_example import CV2PageImage
from pdfplumber.pdf import PDF
from pdfplumber.table import Table
from pdfplumber.table import Row
from pdfplumber.display import PageImage
import cv2
import numpy as np


# setting the image resolution to 200 seems to produce acceptable image visuals.
RESOLUTION = 200
test_path = pl.Path(r"..\pdfs\M68kOpcodes-v2.3.pdf").resolve()


def source_file_specific_logic(page, output_dir:pl.Path,page_num:int):
    """The code here is irrelevant to making the case for encapsulating image processing away from the pdf processing.

    The expected output is that for each table in the source pdf, there will be a unique image in the ouptput dir, along
    with a unique text file mapping the entries on that table.
    """
    tables: List[Table] = page.find_tables()
    for table_idx, tbl in enumerate(tables):
        _table = page.within_bbox(tbl.bbox)
        _table_image = _table.to_image(resolution=200)
        header_boxes = [cell for cell in tbl.rows[0].cells if cell is not None]
        # each cell in header_boxes is a 4-tuple containing the top-left and bottom-right x,y coordinates of
        # that header. E.G.: header_boxes = [(x01,y01,x02,y02),(x11,y12,x13,y14),...,(xn1,yn1,xn2,yn2)]
        # So, column_left_side_bounds = [x01,x11,...,xn1]
        column_left_side_bounds = [cell[0] for cell in header_boxes]
        column_left_side_bounds.append(header_boxes[-1][-2])
        header_txt = [page.within_bbox(cell).extract_text() for cell in header_boxes]
        name = f'{"_".join(header_txt)}_{page_num}_{table_idx}'
        rows = [header_txt]
        row: Row  # annotating type to enable Pycharm's auto-complete
        for row in tbl.rows[1:]:
            _row = []
            for i, left_bound in enumerate(column_left_side_bounds[:-1], 1):
                bbox = (left_bound, row.bbox[1], column_left_side_bounds[i], row.bbox[3])
                try:
                    _row.append(page.within_bbox(bbox).extract_text(x_tolerance=10, y_tolerance=10))
                except TypeError as err:
                    print(f"{type(err)}: {err.args}\n\twhen creating the string sequence for: {name} at {bbox}")
            rows.append(_row)
        _table_image.annotated = cv2.cvtColor(np.array(_table_image.annotated), cv2.COLOR_RGB2BGR)
        try:
            name_fixed = name.replace("  ", "-").replace(".", "_").replace(" ", "-")
            fname = output_dir.joinpath(f"alt_{name_fixed}.png").resolve()
            _table_image.save(str(fname))
            txt_fname = output_dir.joinpath(f"alt_{name_fixed}.txt").resolve()
            with open(str(txt_fname), "w") as f:
                f.write("\n".join(str(row) for row in rows))
        except UnicodeEncodeError as uee:
            print(f"{type(uee)}: {uee.args}\n\tfor table: {name}")


def demo(pdf_path:pl.Path,page_image_type,output_dir_name:str):
    output_dir = pl.Path("./demo_output").resolve().joinpath(output_dir_name)
    output_dir.mkdir(parents=True,exist_ok=True)
    print(f"sample outputs will be saved to:\n\t{output_dir}")
    def inner():
        # pdf: PDF  # annotating type to enable Pycharm's auto-complete
        with PDF.open(pdf_path, page_image_type=page_image_type) as pdf:
            # page: Page # annotating type to enable Pycharm's auto-complete
            for page_num, page in enumerate(pdf.pages):
                source_file_specific_logic(page,output_dir,page_num)
    return inner


if __name__ == '__main__':
    runner = demo(test_path,PageImage,'PILPageImage')
    runner()
    runner = demo(test_path,CV2PageImage,'CV2PageImage')
    runner()
    # the time difference for the trivial image extraction functions above show no meaningful time difference between
    # PIL and opencv, however If the use needed to perform more advanced image manipulations the difference would become
    # apparent. An example case would be to showcase samples of data augmentation for training data in a machine learning
    # paper.
    # from timeit import  timeit
    # default_time = timeit(setup="pil_runner = demo(test_path,PageImage,'PILPageImage')",stmt="pil_runner()",number=5,globals=globals())
    # print(f"time to run default(PIL) variant: {default_time}")
    # cv2_time = timeit(setup="cv2_runner = demo(test_path,CV2PageImage,'CV2PageImage')",stmt="cv2_runner()",number=5,globals=globals())
    # print(f"time to run cv2 variant: {cv2_time}")

``` 