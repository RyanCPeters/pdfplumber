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
