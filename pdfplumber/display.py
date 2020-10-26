from . import utils
from .table import TableFinder

import PIL.Image
import PIL.ImageDraw
import wand.image
from io import BytesIO
import pathlib as pl


class COLORS(object):
    RED = (255, 0, 0)
    GREEN = (0, 255, 0)
    BLUE = (0, 0, 255)
    TRANSPARENT = (0, 0, 0, 0)


DEFAULT_FILL = COLORS.BLUE + (50,)
DEFAULT_STROKE = COLORS.RED + (200,)
DEFAULT_STROKE_WIDTH = 1
DEFAULT_RESOLUTION = 72

image_handler_types = {}

def get_page_image(stream, page_no, resolution):
    """
    For kwargs, see http://docs.wand-py.org/en/latest/wand/image.html#wand.image.Image
    """

    # If we are working with a file object saved to disk
    if hasattr(stream, "name"):
        spec = dict(filename=f"{stream.name}[{page_no}]")

        def postprocess(img):
            return img

    # If we instead are working with a BytesIO stream
    else:
        stream.seek(0)
        spec = dict(file=stream)

        def postprocess(img):
            return wand.image.Image(image=img.sequence[page_no])

    with wand.image.Image(resolution=resolution, **spec) as img_init:
        img = postprocess(img_init)
        if img.alpha_channel:
            img.background_color = wand.image.Color("white")
            img.alpha_channel = "background"
        with img.convert("png") as png:
            im = PIL.Image.open(BytesIO(png.make_blob()))
            if "transparency" in im.info:
                converted = im.convert("RGBA").convert("RGB")
            else:
                converted = im.convert("RGB")
            return converted


class AbstractImageHandler:
    """Meta-interface based on wand.image.Image invocations. This allows users to implement subclasses that utilize
     image processing libraries other than wand or PIL, while maintaining a consistent interface for the pdf parsing
     logic implemented in the pdfplumber library.

     Subclasses must provide custom implementations for the following abstract methods:
        save(self,*args,**kwargs)
        reset(self,mode,**kwargs)
        size(self,**kwargs)
        crop_original(self,cropbox,**kwargs)
        line(self,points,color,width,**kwargs)
        rectangle(self,top_left_pt, color,outline_color,**kwargs)
        ellipse(self, bbox, color, stroke,**kwargs)

    Subclasses must also provide implementations for the property setter methods:
        original_image(self, value)
        annotated_image(self, value)

     """
    def __init__(self, stream, page_no, resolution,
                 optional_source_handler=None) -> None:
        """ImageHandler instances will be created in the same way that images used to be
        produced via calls to get_page_image."""
        self._stream = stream
        self._page_num = page_no
        self._resolution = resolution
        if optional_source_handler is not None:
            self._original = optional_source_handler.original_image
            self._annotated = optional_source_handler.annotated_image
        else:
            self._original = None
            self._annotated = None

    @property
    def stream(self):
        return self._stream

    @property
    def page_number(self):
        return self._page_num - 1

    @property
    def resolution(self):
        return self._resolution

    @property
    def original_image(self):
        """returns a pointer to the underlying original image, unmodified from it's appearance in the source page,
         in whatever format the implementing subclass is working with."""
        return self._original

    @property
    def annotated_image(self):
        """returns a pointer to the underlying annotated image, including any modifications,
         in whatever format the implementing subclass is working with."""
        return self._annotated

    @original_image.setter
    def original_image(self, value):
        raise NotImplementedError("AbstractImageHandler.original_image(value)")

    @annotated_image.setter
    def annotated_image(self, value):
        """Subclasses should overwrite this property setter method"""
        raise NotImplementedError("AbstractImageHandler.annotated_image(value)")

    def save(self,fp, format=None, *args, **params):
        """args and kwargs should be replaced with semantically meaningful parameter names
        when implementing subclasses."""
        raise NotImplementedError("AbstractImageHandler.save(*args,**kwargs)")

    def reset(self,mode=None,**kwargs):
        """reset the annotated image, using the given image mode if applicable for the subclass's
        image type.
        """
        if self._annotated is None:
            if self._original is None:
                self._original = get_page_image(self.stream,self.page_number,self.resolution)

    def size(self,**kwargs):
        """return a 2-tuple of numbers that describe the width and height of the original image
        Subclass implementations may choose to pass specifying parameters calling for the size of
        the annotated image, or possibly the contiguous memory size of the images.
        """
        raise NotImplementedError("AbstractImageHandler.size()")

    def crop_original(self,cropbox,**kwargs):
        """Given cropbox -- a sequence of 4 points -- crop the image data down to a box with
        vertices at those 4 points.

        Note: Subclasses need to call reset after they finish cropping the original image.
              Alternatively, they may simply apply the same cropping procedure to the
              annotated image if they have reason to keep existing annotations within the
              cropped region.
        """
        raise NotImplementedError("AbstractImageHandler.crop_original(cropbox,**kwargs)")

    def line(self,points,color,width,**kwargs):
        """given a sequence of x,y point data for a start point and an end point, draw a line in the given color and
        width connecting those two points."""
        raise NotImplementedError("AbstractImageHandler.line(points_list,color,width,**kwargs)")

    def rectangle(self,bbox, color,outline_color,**kwargs):
        raise NotImplementedError("AbstractImageHandler.rectangle(top_left_pt, color,outline_color,**kwargs)")

    def ellipse(self, bbox, color, stroke,**kwargs):
        raise NotImplementedError("AbstractImageHandler.ellipse(bbox, color, stroke)")


class PILImageHandler(AbstractImageHandler):

    def __init__(self,*args, **kwargs) -> None:
        super().__init__(*args,**kwargs)
        if self.original_image is None:
            self.original_image = get_page_image(self.stream,self.page_number,self.resolution)
        if self.annotated_image is not None:
            self._pil_draw = PIL.ImageDraw.Draw(self.annotated_image, "RGBA")

    @property
    def original_image(self):
        """returns a pointer to the underlying original image, unmodified from it's appearance in the source page,
         in whatever format the implementing subclass is working with."""
        return self._original

    @original_image.setter
    def original_image(self, image_or_mode):
        if isinstance(image_or_mode, PIL.Image.Image):
            self._original = image_or_mode
        elif isinstance(image_or_mode, str):
            tmp = PIL.Image.new(image_or_mode, self._original.size)
            tmp.paste(self._original)
            self._original = tmp
        else:
            raise ValueError("from PILImageHandler.original_image setter, image_mode_or_page is not an instance of:"
                             "\n\tPIL.Image.Image, or string")
        self.reset()

    @property
    def annotated_image(self):
        """By handling image creation and access through getter/setter properties, image manipulation can be detached
        from an explicit dependence upon `wand` and `PIL`."""
        if self._annotated is None:
            self._annotated = self._original.copy()
        return self._annotated

    @annotated_image.setter
    def annotated_image(self, image_or_mode):
        if isinstance(image_or_mode,PIL.Image.Image):
            self._annotated = image_or_mode
            self._pil_draw = PIL.ImageDraw.Draw(self._annotated, self._annotated.mode)
        elif isinstance(image_or_mode,(str or pl.Path)):
            if isinstance(image_or_mode,pl.Path):
                image_or_mode = str(image_or_mode.resolve())
            self._annotated = PIL.Image.new(image_or_mode, self._original.size)
            self._annotated.paste(self._original)
            self._pil_draw = PIL.ImageDraw.Draw(self._annotated, image_or_mode)
        else:
            # image_or_mode isn't a PIL.Image.Image, nor is it a path any sort.
            # It's either a byte array, or something like a numpy array.
            try:
                self._annotated = PIL.Image.fromarray(image_or_mode)
            except:
                self._annotated = PIL.Image.frombuffer(self._annotated.mode,self._annotated.size,image_or_mode)

    @property
    def size(self)->tuple:
        """return a 2-tuple of numbers that describe the width and height of the original image
        Subclass implementations may choose to pass specifying parameters calling for the size of
        the annotated image, or possibly the contiguous memory size of the images.
        """
        return self._original.size

    def save(self, fp, format=None, *args, **params):
        """Saves the annotated image to the given fp object (a bytes buffer or bytes files), in the given format,
        with any additional parameters being passed through the kwargs.

        :param fp: A filename (string), pathlib.Path object or file object.
        :param format: Optional format override.  If omitted, the
           format to use is determined from the filename extension.
           If a file object was used instead of a filename, this
           parameter should always be used.
        :param params: Extra parameters to the image writer.
        :returns: None
        :exception ValueError: If the output format could not be determined
           from the file name.  Use the format option to solve this.
        :exception OSError: If the file could not be written.  The file
           may have been created, and may contain partial data."""
        try:
            self._annotated.save(fp,format,**params)
            return True
        except BaseException as be:
            print(f"PILImageHandler.save encountered {type(be)}: {be.args}")
            return False

    def reset(self, mode=None, **kwargs):
        """reset the annotated image, using the given image mode if applicable for the subclass's
        image type.
        """
        if mode is None:
            mode = self._original.mode
        self._annotated = PIL.Image.new(mode,self._original.size)
        self._annotated.paste(self._original)
        self._pil_draw = PIL.ImageDraw.Draw(self._annotated, mode)

    def crop_original(self, cropbox, **kwargs):
        """Given cropbox -- a sequence of 4 points -- crop the image data down to a box with vertices at those 4 points."""
        self._original = self._original.crop(cropbox)
        self.reset()

    def line(self, points, color, width, **kwargs):
        """given a sequence of x,y point data for a start point and an end point, draw a line in the given color and
        width connecting those two points.

        :param points: 2-tuple of x,y point coordinates, or a 4-tuple as (x0,y0,x1,y1). The two end-points of a
                       line segment
        :param color: the name of the color that should be used when drawing the line (a string)
        :param width: an int defining how many pixels wide the line should be
        :param kwargs: additional parameters that have no use in this implementation, but subclasses may need.
        :return:
        """
        self._pil_draw.line(points, fill=color, width=width)

    def rectangle(self, bbox, color, outline_color, **kwargs):
        """

        :param bbox: 2-tuple of x,y point coordinates, or a 4-tuple as (x0,y0,x1,y1). These points define 2 opposing
                    corners of the bounding box. Should be the top-left corner and bottom-right corners respectively.
        :param color:
        :param outline_color:
        :param kwargs:
        :return:
        """
        self._pil_draw.rectangle(bbox, fill=color, outline=outline_color)

    def ellipse(self, bbox, color, stroke, **kwargs):
        """

        :param bbox: 2-tuple of x,y point coordinates, or a 4-tuple as (x0,y0,x1,y1). These points define 2 opposing
                    corners of the bounding box. Should be the top-left corner and bottom-right corners respectively.
        :param color: string name of color to use when filling in the ellipse
        :param stroke: the color to use for the outline of the ellipse
        :param kwargs: optional keyword arguments, not used in this implementation but subclasses may have a need.
        :return: None
        """
        self._pil_draw.ellipse(bbox, fill=color, outline=stroke)


image_handler_types["PIL"] = PILImageHandler


class BasePageImage(object):
    def __init__(self, page, original=None, resolution=DEFAULT_RESOLUTION,image_handler_type: str or AbstractImageHandler = None):
        resolution = resolution if resolution is not None else DEFAULT_RESOLUTION
        self._valid_image_formats = {"RGBA","RGB"}
        self.page = page
        if original is None:
            self._img_type = image_handler_types.get(image_handler_type,image_handler_type)
        else:
            self._img_type = type(original)
        self._image_handler = self._img_type(page.pdf.stream, page.page_number, resolution, original)
        d = self.page.decimalize
        self.decimalize = d
        if page.is_original:
            self.root = page
            cropped = False
        else:
            self.root = page.root_page
            cropped = page.root_page.bbox != page.bbox
        self.scale = d(self._image_handler.size[0]) / d(self.root.width)
        if cropped:
            cropbox = map(int,(
                (page.bbox[0] - page.root_page.bbox[0]) * self.scale,
                (page.bbox[1] - page.root_page.bbox[1]) * self.scale,
                (page.bbox[2] - page.root_page.bbox[0]) * self.scale,
                (page.bbox[3] - page.root_page.bbox[1]) * self.scale,
            ))
            self._image_handler.crop_original(cropbox)
            # self.original = self.original.crop(map(int, cropbox))
        self.reset()

    @property
    def original(self):
        """returns a pointer to the original image data as taken straight from the source page (possibly cropped)"""
        return self._image_handler.original_image

    @original.setter
    def original(self, value):
        self._image_handler.original_image = value

    @property
    def annotated(self):
        return self._image_handler.annotated_image

    @annotated.setter
    def annotated(self, image_or_mode):
        """Accepts image_or_mode as either a string describing what image mode [PNG,TIF,GIF,... etc.]
        the image should be opened in, or as an already created instance of of a class derived from the
        AbstractImageHandler class.

        :param image_or_mode: A string or an instance of AbstractImageHandler that we can be used to properly build
                              or update self._image_handler.annotated_image.
        :type image_or_mode: Union[str,PIL.Image.Image]
        :return: None
        :rtype: None
        """
        self._image_handler.annotated_image = image_or_mode

    @property
    def draw(self):
        """A backwards compatability method for any user code that directly utlized the PageImage.draw member."""
        return self._image_handler

    def _reproject_bbox(self, bbox):
        x0, top, x1, bottom = bbox
        _x0, _top = self._reproject((x0, top))
        _x1, _bottom = self._reproject((x1, bottom))
        return (_x0, _top, _x1, _bottom)

    def _reproject(self, coord):
        """
        Given an (x0, top) tuple from the *root* coordinate system,
        return an (x0, top) tuple in the *image* coordinate system.
        """
        x0, top = coord
        px0, ptop = self.page.bbox[:2]
        rx0, rtop = self.root.bbox[:2]
        _x0 = (x0 + rx0 - px0) * self.scale
        _top = (top + rtop - ptop) * self.scale
        return (_x0, _top)

    def reset(self):
        # self.annotated = PIL.Image.new(self.original.mode, self.original.size)
        # self.annotated.paste(self.original)
        # self.draw = PIL.ImageDraw.Draw(self.annotated, "RGBA")
        # updated for encapsulation of image manipulation
        self._image_handler.reset("RGBA")  # can also just pass None
        return self

    def copy(self):
        return self.__class__(self.page, self._image_handler,self._image_handler.resolution)

    def draw_line(
            self, points_or_obj, stroke=DEFAULT_STROKE, stroke_width=DEFAULT_STROKE_WIDTH
    ):
        if isinstance(points_or_obj, (tuple, list)):
            points = points_or_obj
        elif type(points_or_obj) == dict and "points" in points_or_obj:
            points = points_or_obj["points"]
        else:
            obj = points_or_obj
            points = ((obj["x0"], obj["top"]), (obj["x1"], obj["bottom"]))
        # updated for encapsulation of image manipulation
        self._image_handler.line(list(map(self._reproject, points)), color=stroke, width=stroke_width)
        return self

    def draw_lines(self, list_of_lines, **kwargs):
        for x in utils.to_list(list_of_lines):
            self.draw_line(x, **kwargs)
        return self

    def draw_vline(
            self, location, stroke=DEFAULT_STROKE, stroke_width=DEFAULT_STROKE_WIDTH
    ):
        points = (location, self.page.bbox[1], location, self.page.bbox[3])
        # updated for encapsulation of image manipulation
        self._image_handler.line(list(map(self._reproject, points)), color=stroke, width=stroke_width)
        return self

    def draw_vlines(self, locations, **kwargs):
        for x in utils.to_list(locations):
            self.draw_vline(x, **kwargs)
        return self

    def draw_hline(
            self, location, stroke=DEFAULT_STROKE, stroke_width=DEFAULT_STROKE_WIDTH
    ):
        points = (self.page.bbox[0], location, self.page.bbox[2], location)
        self._image_handler.line(self._reproject_bbox(points), color=stroke, width=stroke_width)
        return self

    def draw_hlines(self, locations, **kwargs):
        for x in utils.to_list(locations):
            self.draw_hline(x, **kwargs)
        return self

    def draw_rect(
            self,
            bbox_or_obj,
            fill=DEFAULT_FILL,
            stroke=DEFAULT_STROKE,
            stroke_width=DEFAULT_STROKE_WIDTH,
    ):
        if isinstance(bbox_or_obj, (tuple, list)):
            bbox = bbox_or_obj
        else:
            obj = bbox_or_obj
            bbox = (obj["x0"], obj["top"], obj["x1"], obj["bottom"])

        x0, top, x1, bottom = bbox
        half = self.decimalize(stroke_width / 2)
        x0 += half
        top += half
        x1 -= half
        bottom -= half

        self._image_handler.rectangle(
            self._reproject_bbox((x0, top, x1, bottom)), fill, COLORS.TRANSPARENT
        )

        if stroke_width > 0:
            segments = [
                ((x0, top), (x1, top)),  # top
                ((x0, bottom), (x1, bottom)),  # bottom
                ((x0, top), (x0, bottom)),  # left
                ((x1, top), (x1, bottom)),  # right
            ]
            self.draw_lines(segments, stroke=stroke, stroke_width=stroke_width)
        return self

    def draw_rects(self, list_of_rects, **kwargs):
        for x in utils.to_list(list_of_rects):
            self.draw_rect(x, **kwargs)
        return self

    def draw_circle(
            self, center_or_obj, radius=5, fill=DEFAULT_FILL, stroke=DEFAULT_STROKE
    ):
        if isinstance(center_or_obj, (tuple, list)):
            center = center_or_obj
        else:
            obj = center_or_obj
            center = ((obj["x0"] + obj["x1"]) / 2, (obj["top"] + obj["bottom"]) / 2)
        cx, cy = center
        bbox = self.decimalize((cx - radius, cy - radius, cx + radius, cy + radius))
        self._image_handler.ellipse(self._reproject_bbox(bbox), fill, stroke)
        return self

    def draw_circles(self, list_of_circles, **kwargs):
        for x in utils.to_list(list_of_circles):
            self.draw_circle(x, **kwargs)
        return self

    def save(self, *args, **kwargs):
        self._image_handler.save(*args, **kwargs)

    def debug_table(
            self, table, fill=DEFAULT_FILL, stroke=DEFAULT_STROKE, stroke_width=1
    ):
        """
        Outline all found tables.
        """
        self.draw_rects(
            table.cells, fill=fill, stroke=stroke, stroke_width=stroke_width
        )
        return self

    def debug_tablefinder(self, tf={}):
        if isinstance(tf, TableFinder):
            pass
        elif isinstance(tf, dict):
            tf = self.page.debug_tablefinder(tf)
        else:
            raise ValueError(
                "Argument must be instance of TableFinder"
                "or a TableFinder settings dict."
            )

        for table in tf.tables:
            self.debug_table(table)

        self.draw_lines(tf.edges, stroke_width=1)

        self.draw_circles(
            tf.intersections.keys(),
            fill=COLORS.TRANSPARENT,
            stroke=COLORS.BLUE + (200,),
            radius=3,
        )
        return self

    def outline_words(
            self,
            stroke=DEFAULT_STROKE,
            fill=DEFAULT_FILL,
            stroke_width=DEFAULT_STROKE_WIDTH,
            x_tolerance=utils.DEFAULT_X_TOLERANCE,
            y_tolerance=utils.DEFAULT_Y_TOLERANCE,
    ):

        words = self.page.extract_words(
            x_tolerance=x_tolerance, y_tolerance=y_tolerance
        )
        self.draw_rects(words, stroke=stroke, fill=fill, stroke_width=stroke_width)
        return self

    def outline_chars(
            self,
            stroke=(255, 0, 0, 255),
            fill=(255, 0, 0, int(255 / 4)),
            stroke_width=DEFAULT_STROKE_WIDTH,
    ):

        self.draw_rects(
            self.page.chars, stroke=stroke, fill=fill, stroke_width=stroke_width
        )
        return self

    def _repr_png_(self):
        with BytesIO() as b:
            self._image_handler.save(b, "PNG")
            return b.getvalue()


class PILPageImage(BasePageImage):
    """The PIL specific implementation of the AbstractPageImage class. This subclass only changes how the object is
    instantiated, specifying the image handler type that it accepts in order to assure we only use PIL."""
    def __init__(self, page, original: PILImageHandler = None, resolution=None,
                 image_handler_type: str or PILImageHandler = 'PIL'):
        resolution = resolution if resolution is not None else DEFAULT_RESOLUTION
        image_handler_type = image_handler_types.get(image_handler_type,PILImageHandler)
        super().__init__(page, original, resolution, image_handler_type)

PageImage = PILPageImage

# class PageImage(object):
#     def __init__(self, page, original=None, resolution=DEFAULT_RESOLUTION):
#         self.page = page
#         if original is None:
#             self.original = get_page_image(
#                 page.pdf.stream, page.page_number - 1, resolution
#             )
#         else:
#             self.original = original
#
#         d = self.page.decimalize
#         self.decimalize = d
#         if page.is_original:
#             self.root = page
#             cropped = False
#         else:
#             self.root = page.root_page
#             cropped = page.root_page.bbox != page.bbox
#         self.scale = d(self.original.size[0]) / d(self.root.width)
#         if cropped:
#             cropbox = (
#                 (page.bbox[0] - page.root_page.bbox[0]) * self.scale,
#                 (page.bbox[1] - page.root_page.bbox[1]) * self.scale,
#                 (page.bbox[2] - page.root_page.bbox[0]) * self.scale,
#                 (page.bbox[3] - page.root_page.bbox[1]) * self.scale,
#             )
#             self.original = self.original.crop(map(int, cropbox))
#         self.reset()
#
#     def _reproject_bbox(self, bbox):
#         x0, top, x1, bottom = bbox
#         _x0, _top = self._reproject((x0, top))
#         _x1, _bottom = self._reproject((x1, bottom))
#         return (_x0, _top, _x1, _bottom)
#
#     def _reproject(self, coord):
#         """
#         Given an (x0, top) tuple from the *root* coordinate system,
#         return an (x0, top) tuple in the *image* coordinate system.
#         """
#         x0, top = coord
#         px0, ptop = self.page.bbox[:2]
#         rx0, rtop = self.root.bbox[:2]
#         _x0 = (x0 + rx0 - px0) * self.scale
#         _top = (top + rtop - ptop) * self.scale
#         return (_x0, _top)
#
#     def reset(self):
#         self.annotated = PIL.Image.new(self.original.mode, self.original.size)
#         self.annotated.paste(self.original)
#         self.draw = PIL.ImageDraw.Draw(self.annotated, "RGBA")
#         return self
#
#     def copy(self):
#         return self.__class__(self.page, self.original)
#
#     def draw_line(
#         self, points_or_obj, stroke=DEFAULT_STROKE, stroke_width=DEFAULT_STROKE_WIDTH
#     ):
#         if isinstance(points_or_obj, (tuple, list)):
#             points = points_or_obj
#         elif type(points_or_obj) == dict and "points" in points_or_obj:
#             points = points_or_obj["points"]
#         else:
#             obj = points_or_obj
#             points = ((obj["x0"], obj["top"]), (obj["x1"], obj["bottom"]))
#         self.draw.line(
#             list(map(self._reproject, points)), fill=stroke, width=stroke_width
#         )
#         return self
#
#     def draw_lines(self, list_of_lines, **kwargs):
#         for x in utils.to_list(list_of_lines):
#             self.draw_line(x, **kwargs)
#         return self
#
#     def draw_vline(
#         self, location, stroke=DEFAULT_STROKE, stroke_width=DEFAULT_STROKE_WIDTH
#     ):
#         points = (location, self.page.bbox[1], location, self.page.bbox[3])
#         self.draw.line(self._reproject_bbox(points), fill=stroke, width=stroke_width)
#         return self
#
#     def draw_vlines(self, locations, **kwargs):
#         for x in utils.to_list(locations):
#             self.draw_vline(x, **kwargs)
#         return self
#
#     def draw_hline(
#         self, location, stroke=DEFAULT_STROKE, stroke_width=DEFAULT_STROKE_WIDTH
#     ):
#         points = (self.page.bbox[0], location, self.page.bbox[2], location)
#         self.draw.line(self._reproject_bbox(points), fill=stroke, width=stroke_width)
#         return self
#
#     def draw_hlines(self, locations, **kwargs):
#         for x in utils.to_list(locations):
#             self.draw_hline(x, **kwargs)
#         return self
#
#     def draw_rect(
#         self,
#         bbox_or_obj,
#         fill=DEFAULT_FILL,
#         stroke=DEFAULT_STROKE,
#         stroke_width=DEFAULT_STROKE_WIDTH,
#     ):
#         if isinstance(bbox_or_obj, (tuple, list)):
#             bbox = bbox_or_obj
#         else:
#             obj = bbox_or_obj
#             bbox = (obj["x0"], obj["top"], obj["x1"], obj["bottom"])
#
#         x0, top, x1, bottom = bbox
#         half = self.decimalize(stroke_width / 2)
#         x0 += half
#         top += half
#         x1 -= half
#         bottom -= half
#
#         self.draw.rectangle(
#             self._reproject_bbox((x0, top, x1, bottom)), fill, COLORS.TRANSPARENT
#         )
#
#         if stroke_width > 0:
#             segments = [
#                 ((x0, top), (x1, top)),  # top
#                 ((x0, bottom), (x1, bottom)),  # bottom
#                 ((x0, top), (x0, bottom)),  # left
#                 ((x1, top), (x1, bottom)),  # right
#             ]
#             self.draw_lines(segments, stroke=stroke, stroke_width=stroke_width)
#         return self
#
#     def draw_rects(self, list_of_rects, **kwargs):
#         for x in utils.to_list(list_of_rects):
#             self.draw_rect(x, **kwargs)
#         return self
#
#     def draw_circle(
#         self, center_or_obj, radius=5, fill=DEFAULT_FILL, stroke=DEFAULT_STROKE
#     ):
#         if isinstance(center_or_obj, (tuple, list)):
#             center = center_or_obj
#         else:
#             obj = center_or_obj
#             center = ((obj["x0"] + obj["x1"]) / 2, (obj["top"] + obj["bottom"]) / 2)
#         cx, cy = center
#         bbox = self.decimalize((cx - radius, cy - radius, cx + radius, cy + radius))
#         self.draw.ellipse(self._reproject_bbox(bbox), fill, stroke)
#         return self
#
#     def draw_circles(self, list_of_circles, **kwargs):
#         for x in utils.to_list(list_of_circles):
#             self.draw_circle(x, **kwargs)
#         return self
#
#     def save(self, *args, **kwargs):
#         return self.annotated.save(*args, **kwargs)
#
#     def debug_table(
#         self, table, fill=DEFAULT_FILL, stroke=DEFAULT_STROKE, stroke_width=1
#     ):
#         """
#         Outline all found tables.
#         """
#         self.draw_rects(
#             table.cells, fill=fill, stroke=stroke, stroke_width=stroke_width
#         )
#         return self
#
#     def debug_tablefinder(self, tf={}):
#         if isinstance(tf, TableFinder):
#             pass
#         elif isinstance(tf, dict):
#             tf = self.page.debug_tablefinder(tf)
#         else:
#             raise ValueError(
#                 "Argument must be instance of TableFinder"
#                 "or a TableFinder settings dict."
#             )
#
#         for table in tf.tables:
#             self.debug_table(table)
#
#         self.draw_lines(tf.edges, stroke_width=1)
#
#         self.draw_circles(
#             tf.intersections.keys(),
#             fill=COLORS.TRANSPARENT,
#             stroke=COLORS.BLUE + (200,),
#             radius=3,
#         )
#         return self
#
#     def outline_words(
#         self,
#         stroke=DEFAULT_STROKE,
#         fill=DEFAULT_FILL,
#         stroke_width=DEFAULT_STROKE_WIDTH,
#         x_tolerance=utils.DEFAULT_X_TOLERANCE,
#         y_tolerance=utils.DEFAULT_Y_TOLERANCE,
#     ):
#
#         words = self.page.extract_words(
#             x_tolerance=x_tolerance, y_tolerance=y_tolerance
#         )
#         self.draw_rects(words, stroke=stroke, fill=fill, stroke_width=stroke_width)
#         return self
#
#     def outline_chars(
#         self,
#         stroke=(255, 0, 0, 255),
#         fill=(255, 0, 0, int(255 / 4)),
#         stroke_width=DEFAULT_STROKE_WIDTH,
#     ):
#
#         self.draw_rects(
#             self.page.chars, stroke=stroke, fill=fill, stroke_width=stroke_width
#         )
#         return self
#
#     def _repr_png_(self):
#         b = BytesIO()
#         self.annotated.save(b, "PNG")
#         return b.getvalue()