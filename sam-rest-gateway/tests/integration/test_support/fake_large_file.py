import io

class FakeLargeFile(io.IOBase):
    """
    A file-like object that simulates a large file of a given size
    without allocating all the bytes in memory.
    """

    def __init__(self, size: int, fill_byte: bytes = b"a"):
        self._size = size
        self._pos = 0
        self._fill_byte = fill_byte

    def read(self, size: int = -1) -> bytes:
        if self._pos >= self._size:
            return b""
        
        if size == -1:
            size = self._size - self._pos
        
        bytes_to_read = min(size, self._size - self._pos)
        data = self._fill_byte * bytes_to_read
        self._pos += bytes_to_read
        return data

    def seek(self, pos: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            self._pos = pos
        elif whence == io.SEEK_CUR:
            self._pos += pos
        elif whence == io.SEEK_END:
            self._pos = self._size + pos
        
        self._pos = max(0, min(self._pos, self._size))
        return self._pos

    def tell(self) -> int:
        return self._pos

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True
        
    def writable(self) -> bool:
        return False

    def __len__(self) -> int:
        return self._size
