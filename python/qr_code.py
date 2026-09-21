"""QR Code Model 2 encoder (byte mode, ECC M) for pairing URLs."""

from __future__ import annotations

# Version, (ec_per_block, group1_blocks, group1_data, group2_blocks, group2_data)
_ECC_M = {
    1: (10, 1, 16, 0, 0),
    2: (16, 1, 28, 0, 0),
    3: (26, 1, 44, 0, 0),
    4: (18, 2, 32, 0, 0),
    5: (24, 2, 43, 0, 0),
    6: (16, 4, 27, 0, 0),
    7: (18, 4, 31, 0, 0),
    8: (22, 2, 38, 2, 39),
    9: (22, 3, 36, 2, 37),
    10: (26, 4, 43, 1, 44),
}

_ALIGN = {
    2: (6, 18),
    3: (6, 22),
    4: (6, 26),
    5: (6, 30),
    6: (6, 34),
    7: (6, 22, 38),
    8: (6, 24, 42),
    9: (6, 26, 46),
    10: (6, 28, 50),
}

_EXP = [0] * 512
_LOG = [0] * 256


def _init_gf():
    value = 1
    for index in range(255):
        _EXP[index] = value
        _LOG[value] = index
        value <<= 1
        if value & 0x100:
            value ^= 0x11D
    for index in range(255, 512):
        _EXP[index] = _EXP[index - 255]


_init_gf()


def _gf_mul(left, right):
    if left == 0 or right == 0:
        return 0
    return _EXP[_LOG[left] + _LOG[right]]


def _gf_pow(base, power):
    return _EXP[(_LOG[base] * power) % 255] if base else 0


def _poly_mul(left, right):
    out = [0] * (len(left) + len(right) - 1)
    for i, a in enumerate(left):
        for j, b in enumerate(right):
            out[i + j] ^= _gf_mul(a, b)
    return out


def _rs_generator(degree):
    poly = [1]
    for index in range(degree):
        poly = _poly_mul(poly, [1, _gf_pow(2, index)])
    return poly


def _rs_encode(data, degree):
    gen = _rs_generator(degree)
    info = list(data) + [0] * degree
    for index in range(len(data)):
        factor = info[index]
        if factor == 0:
            continue
        for pos, coef in enumerate(gen):
            info[index + pos] ^= _gf_mul(coef, factor)
    return info[-degree:]


def _version_for(nbytes):
    # mode(4) + length(8 or 16) + data + terminator, packed into data codewords
    for version in range(1, 11):
        ec, g1, d1, g2, d2 = _ECC_M[version]
        capacity = g1 * d1 + g2 * d2
        length_bits = 8 if version < 10 else 16
        bits = 4 + length_bits + nbytes * 8 + 4
        if (bits + 7) // 8 <= capacity:
            return version
    raise ValueError("Text is too long for a pairing QR code.")


def _bitstream(data, version):
    length_bits = 8 if version < 10 else 16
    bits = [0, 1, 0, 0]
    length = len(data)
    bits.extend((length >> shift) & 1 for shift in range(length_bits - 1, -1, -1))
    for byte in data:
        bits.extend((byte >> shift) & 1 for shift in range(7, -1, -1))
    bits.extend([0] * 4)
    while len(bits) % 8:
        bits.append(0)
    return bits


def _data_codewords(data, version):
    ec, g1, d1, g2, d2 = _ECC_M[version]
    capacity = g1 * d1 + g2 * d2
    bits = _bitstream(data, version)
    words = []
    for index in range(0, len(bits), 8):
        chunk = bits[index:index + 8]
        value = 0
        for bit in chunk:
            value = (value << 1) | bit
        words.append(value)
    pad = (0xEC, 0x11)
    extra = 0
    while len(words) < capacity:
        words.append(pad[extra % 2])
        extra += 1
    return words[:capacity]


def _interleave(data, version):
    ec, g1, d1, g2, d2 = _ECC_M[version]
    blocks = []
    offset = 0
    for _ in range(g1):
        block = data[offset:offset + d1]
        blocks.append(block + _rs_encode(block, ec))
        offset += d1
    for _ in range(g2):
        block = data[offset:offset + d2]
        blocks.append(block + _rs_encode(block, ec))
        offset += d2
    data_len = max(len(block) - ec for block in blocks)
    out = []
    for index in range(data_len):
        for block in blocks:
            if index < len(block) - ec:
                out.append(block[index])
    for index in range(ec):
        for block in blocks:
            out.append(block[len(block) - ec + index])
    return out


def _size(version):
    return 21 + 4 * (version - 1)


def _finder(grid, row, col):
    pattern = (
        (1, 1, 1, 1, 1, 1, 1),
        (1, 0, 0, 0, 0, 0, 1),
        (1, 0, 1, 1, 1, 0, 1),
        (1, 0, 1, 1, 1, 0, 1),
        (1, 0, 1, 1, 1, 0, 1),
        (1, 0, 0, 0, 0, 0, 1),
        (1, 1, 1, 1, 1, 1, 1),
    )
    for dy, line in enumerate(pattern):
        for dx, bit in enumerate(line):
            grid[row + dy][col + dx] = bit


def _reserve(reserved, row, col, height, width):
    size = len(reserved)
    for y in range(row, row + height):
        for x in range(col, col + width):
            if 0 <= y < size and 0 <= x < size:
                reserved[y][x] = 1


def _alignment(grid, reserved, version):
    positions = _ALIGN.get(version, ())
    pattern = (
        (1, 1, 1, 1, 1),
        (1, 0, 0, 0, 1),
        (1, 0, 1, 0, 1),
        (1, 0, 0, 0, 1),
        (1, 1, 1, 1, 1),
    )
    for row in positions:
        for col in positions:
            if reserved[row][col]:
                continue
            for dy, line in enumerate(pattern):
                for dx, bit in enumerate(line):
                    grid[row - 2 + dy][col - 2 + dx] = bit
                    reserved[row - 2 + dy][col - 2 + dx] = 1


def _place_function(grid, reserved, version):
    size = len(grid)
    for row, col in ((0, 0), (0, size - 7), (size - 7, 0)):
        _finder(grid, row, col)
        _reserve(reserved, row, col, 7, 7)
    _reserve(reserved, 0, 7, 8, 1)
    _reserve(reserved, 7, 0, 1, 8)
    _reserve(reserved, 0, size - 8, 8, 8)
    _reserve(reserved, size - 8, 0, 8, 8)
    for index in range(size):
        bit = index % 2 == 0
        if not reserved[6][index]:
            grid[6][index] = bit
            reserved[6][index] = 1
        if not reserved[index][6]:
            grid[index][6] = bit
            reserved[index][6] = 1
    _alignment(grid, reserved, version)
    _reserve(reserved, 8, 0, 1, 9)
    _reserve(reserved, 0, 8, 8, 1)
    _reserve(reserved, 8, size - 8, 1, 8)
    _reserve(reserved, size - 8, 8, 8, 1)
    grid[size - 8][8] = 1
    reserved[size - 8][8] = 1
    if version >= 7:
        _reserve(reserved, 0, size - 11, 6, 3)
        _reserve(reserved, size - 11, 0, 3, 6)


def _mask_bit(kind, row, col):
    if kind == 0:
        return (row + col) % 2 == 0
    if kind == 1:
        return row % 2 == 0
    if kind == 2:
        return col % 3 == 0
    if kind == 3:
        return (row + col) % 3 == 0
    if kind == 4:
        return (row // 2 + col // 3) % 2 == 0
    if kind == 5:
        return (row * col) % 2 + (row * col) % 3 == 0
    if kind == 6:
        return ((row * col) % 2 + (row * col) % 3) % 2 == 0
    return ((row + col) % 2 + (row * col) % 3) % 2 == 0


def _place_data(grid, reserved, codewords, mask):
    size = len(grid)
    bits = []
    for word in codewords:
        bits.extend((word >> shift) & 1 for shift in range(7, -1, -1))
    cursor = 0
    direction = -1
    col = size - 1
    while col > 0:
        if col == 6:
            col -= 1
        for row in range(size - 1, -1, -1) if direction < 0 else range(size):
            for dx in (0, -1):
                x = col + dx
                if reserved[row][x]:
                    continue
                bit = bits[cursor] if cursor < len(bits) else 0
                cursor += 1
                if _mask_bit(mask, row, x):
                    bit ^= 1
                grid[row][x] = bit
        direction *= -1
        col -= 2


def _format_bits(mask):
    data = mask  # ECC M = 00
    rem = data << 10
    gen = 0b10100110111
    for shift in range(4, -1, -1):
        if rem & (1 << (shift + 10)):
            rem ^= gen << shift
    return (data << 10 | rem) ^ 0x5412


def _version_bits(version):
    rem = version << 12
    gen = 0b1111100100101
    for shift in range(5, -1, -1):
        if rem & (1 << (shift + 12)):
            rem ^= gen << shift
    return version << 12 | rem


def _draw_format(grid, mask):
    bits = _format_bits(mask)
    size = len(grid)
    coords_a = [
        (8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5), (8, 7), (8, 8),
        (7, 8), (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8),
    ]
    coords_b = [
        (size - 1, 8), (size - 2, 8), (size - 3, 8), (size - 4, 8),
        (size - 5, 8), (size - 6, 8), (size - 7, 8),
        (8, size - 8), (8, size - 7), (8, size - 6), (8, size - 5),
        (8, size - 4), (8, size - 3), (8, size - 2), (8, size - 1),
    ]
    for index, (row, col) in enumerate(coords_a):
        grid[row][col] = (bits >> (14 - index)) & 1
    for index, (row, col) in enumerate(coords_b):
        grid[row][col] = (bits >> (14 - index)) & 1


def _draw_version(grid, version):
    if version < 7:
        return
    bits = _version_bits(version)
    size = len(grid)
    index = 17
    for col in range(6):
        for row in range(3):
            bit = (bits >> index) & 1
            index -= 1
            grid[size - 11 + row][col] = bit
            grid[col][size - 11 + row] = bit


def _penalty(grid):
    size = len(grid)
    score = 0
    for row in grid:
        run = 1
        for index in range(1, size):
            if row[index] == row[index - 1]:
                run += 1
            else:
                if run >= 5:
                    score += run - 2
                run = 1
        if run >= 5:
            score += run - 2
    for col in range(size):
        run = 1
        for index in range(1, size):
            if grid[index][col] == grid[index - 1][col]:
                run += 1
            else:
                if run >= 5:
                    score += run - 2
                run = 1
        if run >= 5:
            score += run - 2
    for row in range(size - 1):
        for col in range(size - 1):
            if grid[row][col] == grid[row][col + 1] == grid[row + 1][col] == grid[row + 1][col + 1]:
                score += 3
    finder = (1, 0, 1, 1, 1, 0, 1)
    for row in range(size):
        line = grid[row]
        for col in range(size - 6):
            window = tuple(line[col:col + 7])
            if window == finder:
                left = col >= 4 and line[col - 4:col] == [0, 0, 0, 0]
                right = col + 10 <= size and line[col + 7:col + 11] == [0, 0, 0, 0]
                if left or right:
                    score += 40
    for col in range(size):
        column = [grid[row][col] for row in range(size)]
        for row in range(size - 6):
            window = tuple(column[row:row + 7])
            if window == finder:
                up = row >= 4 and column[row - 4:row] == [0, 0, 0, 0]
                down = row + 10 <= size and column[row + 7:row + 11] == [0, 0, 0, 0]
                if up or down:
                    score += 40
    dark = sum(sum(row) for row in grid)
    percent = abs((dark * 100) // (size * size) - 50) // 5
    score += percent * 10
    return score


def matrix(text):
    """Return a square 0/1 module grid for *text* (UTF-8 byte mode, ECC M)."""
    payload = (text or "").encode("utf-8")
    version = _version_for(len(payload))
    words = _interleave(_data_codewords(payload, version), version)
    size = _size(version)
    best = None
    best_score = None
    for mask in range(8):
        grid = [[0] * size for _ in range(size)]
        reserved = [[0] * size for _ in range(size)]
        _place_function(grid, reserved, version)
        _place_data(grid, reserved, words, mask)
        _draw_format(grid, mask)
        _draw_version(grid, version)
        score = _penalty(grid)
        if best_score is None or score < best_score:
            best = grid
            best_score = score
    return best


def draw_on_canvas(canvas, text, size=196):
    """Paint *text* as a QR code onto a Tk canvas. Returns False if empty."""
    if canvas is None:
        return False
    canvas.delete("all")
    if not text:
        return False
    modules = matrix(text)
    n = len(modules)
    quiet = 4
    total = n + quiet * 2
    scale = max(2, size // total)
    _paint(canvas, modules, scale, quiet)
    return True


def _paint(canvas, modules, scale, quiet):
    n = len(modules)
    total = n + quiet * 2
    canvas.configure(
        width=total * scale,
        height=total * scale,
        bg="white",
        highlightthickness=0,
    )
    canvas.create_rectangle(0, 0, total * scale, total * scale, fill="white", outline="")
    for y, row in enumerate(modules):
        for x, bit in enumerate(row):
            if not bit:
                continue
            x0 = (x + quiet) * scale
            y0 = (y + quiet) * scale
            canvas.create_rectangle(
                x0, y0, x0 + scale, y0 + scale, fill="black", outline="black",
            )
