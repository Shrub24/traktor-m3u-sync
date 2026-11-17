from mutagen import FileType

class Picture:
    data: bytes

class FLAC(FileType):
    pictures: list[Picture]
