import base64
import io
import zipfile
from app.skills.packages import archive_files

stream = io.BytesIO()
with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
    archive.writestr('SKILL.md', '---\nname: broken\ndescription: Broken archive fixture\n---\nRead carefully.')
body = bytearray(stream.getvalue())
with zipfile.ZipFile(io.BytesIO(body)) as archive:
    info = archive.infolist()[0]
    offset = info.header_offset + 30 + len(info.filename.encode()) + len(info.extra)
    body[offset:offset + info.compress_size] = b'\xff' * info.compress_size
try:
    archive_files(base64.b64encode(body).decode())
except Exception as error:
    print(type(error).__module__ + '.' + type(error).__name__ + ': ' + str(error))
