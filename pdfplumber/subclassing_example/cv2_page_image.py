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