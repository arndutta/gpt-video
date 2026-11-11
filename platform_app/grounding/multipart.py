"""A document is accepted only after a complete multipart message has been received."""

from contextlib import asynccontextmanager

from starlette.formparsers import MultiPartException, MultiPartParser


class CompleteMultipartParser(MultiPartParser):
    """The underlying parser's finalize() does not reject every truncated message."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.complete = False

    def on_end(self):
        self.complete = True

    async def parse(self):
        try:
            form = await super().parse()
            if not self.complete:
                raise MultiPartException("The multipart upload was incomplete.")
            return form
        except BaseException:
            # This includes a file whose part never ended and therefore is absent from form.items.
            # These parser-owned handles are also used by Starlette's own failure cleanup.
            for file in self._files_to_close_on_error:
                file.close()
            raise


@asynccontextmanager
async def upload_form(request):
    parser = CompleteMultipartParser(request.headers, request.stream(), max_files=1,
                                     max_fields=4, max_part_size=4096)
    form = await parser.parse()
    try:
        yield form
    finally:
        await form.close()
