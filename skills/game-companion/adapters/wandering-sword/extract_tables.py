#!/usr/bin/env python3
"""extract_tables: read Wandering Sword's DataTables out of the player's own game files into readable JSON.

  extract_tables.py        unpack JH/Tables from the game pak with repak, write <DATA_DIR>/<Table>.json

Each output file is {RowName: {Field: value}}. Enums stay as "EType::Value", FText becomes its source string,
soft object paths become ".<path>". The game data stays on this machine; nothing here is redistributed.
repak (trumank/repak, MIT) is downloaded once into the cache and checked against a pinned SHA-256.
Needs only the Python standard library. UE 4.26 cooked assets with tagged properties.
"""
import io, json, os, platform, shutil, struct, subprocess, sys, tarfile, tempfile, urllib.request, zipfile, hashlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
from common import DATA_DIR, HOME, game_dir

# ===== CONFIG =====
PAK_REL = "Wandering_Sword/Content/Paks/Wandering_Sword-WindowsNoEditor.pak"
TABLES_IN_PAK = "Wandering_Sword/Content/JH/Tables"
REQUIRED = ["Items", "NPCs", "Quests", "Maps", "Skills", "DropPools", "NPCAggregation"]  # what wsq.py reads
REPAK = {  # pinned release v0.2.3: (url, sha256)
    "Windows": ("https://github.com/trumank/repak/releases/download/v0.2.3/repak_cli-x86_64-pc-windows-msvc.zip",
                "6720d602144d75df477a99d5bedb6ea780997546afc335901d4937cafeaa73fa"),
    "Linux": ("https://github.com/trumank/repak/releases/download/v0.2.3/repak_cli-x86_64-unknown-linux-gnu.tar.xz",
              "933bdb8e26f34e8fd70ea50201efca39df041de58aa83b1cd6eb83da124a2046"),
}
# ==================

TOOLS = HOME / "tools"


# ---------- repak ----------
def repak():
    exe = TOOLS / ("repak.exe" if os.name == "nt" else "repak")
    if exe.exists():
        return exe
    url, sha = REPAK[platform.system()]
    print(f"下载 repak：{url}")
    data = urllib.request.urlopen(url, timeout=60).read()
    if hashlib.sha256(data).hexdigest() != sha:
        sys.exit("repak 下载内容的 SHA-256 不对，已停止。")
    TOOLS.mkdir(parents=True, exist_ok=True)
    if url.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            member = next(n for n in z.namelist() if n.endswith("repak.exe"))
            exe.write_bytes(z.read(member))
    else:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:xz") as t:
            member = next(m for m in t.getmembers() if m.name.endswith("/repak"))
            exe.write_bytes(t.extractfile(member).read())
        exe.chmod(0o755)
    return exe


# ---------- UE 4.26 package reader ----------
class Reader:
    def __init__(self, data, names=(), imports=()):
        self.b, self.p, self.names, self.imports = data, 0, names, imports

    def take(self, n):
        if self.p + n > len(self.b):
            raise EOFError
        self.p += n
        return self.b[self.p - n:self.p]

    def unpack(self, fmt):
        return struct.unpack(fmt, self.take(struct.calcsize(fmt)))[0]

    def i32(self): return self.unpack("<i")

    def string(self):
        n = self.i32()
        if n == 0:
            return None
        if n > 0:
            return self.take(n)[:-1].decode("latin-1")
        return self.take(-2 * n)[:-2].decode("utf-16-le", "replace")

    def name(self):
        i, num = self.i32(), self.i32()
        return f"{self.names[i]}_{num - 1}" if num else self.names[i]


def f32(x):
    """Shortest decimal that round-trips the float32, as .NET prints it."""
    for digits in range(1, 10):
        s = float(f"{x:.{digits}g}")
        if struct.pack("<f", s) == struct.pack("<f", x):
            return s
    return x


def clean_name(n):
    # Blueprint struct fields look like "Name_12_ABCDEF0123..."; keep only the readable part.
    head, _, guid = n.rpartition("_")
    if len(guid) == 32 and all(c in "0123456789ABCDEF" for c in guid):
        base, _, num = head.rpartition("_")
        if num.isdigit() and base:
            return base
    return n


SCALAR = {"IntProperty": "<i", "Int8Property": "<b", "Int16Property": "<h", "Int64Property": "<q",
          "UInt16Property": "<H", "UInt32Property": "<I", "UInt64Property": "<Q", "DoubleProperty": "<d"}


def text(r):
    r.i32()  # flags
    history = r.unpack("<b")
    if history == -1:
        return r.string() if r.i32() else None
    if history == 0:
        r.string()  # namespace
        key, source = r.string(), r.string()
        return source if source is not None else key
    if history == 11:
        table = r.name()
        return f"@{table}:{r.string()}"
    raise ValueError(f"FText history {history}")


def obj(r):
    i = r.i32()
    if i == 0:
        return None
    return r.imports[-i - 1] if i < 0 else f"export:{i}"


def element(r, typ, elem_size=None):
    """A value without a tag (inside an array, set or map)."""
    if typ in SCALAR:
        return r.unpack(SCALAR[typ])
    if typ == "FloatProperty":
        return f32(r.unpack("<f"))
    if typ == "BoolProperty":
        return r.take(1)[0] != 0
    if typ == "ByteProperty":
        return r.take(1)[0] if elem_size == 1 else r.name()
    if typ in ("NameProperty", "EnumProperty"):
        return r.name()
    if typ == "StrProperty":
        return r.string()
    if typ == "TextProperty":
        return text(r)
    if typ in ("SoftObjectProperty", "SoftClassProperty"):
        path = r.name()
        r.string()  # sub path
        return "." + path
    if typ in ("ObjectProperty", "ClassProperty", "WeakObjectProperty", "LazyObjectProperty"):
        return obj(r)
    if typ == "StructProperty":
        return props(r)
    raise ValueError(f"unsupported element type {typ}")


def struct_value(r, struct_name):
    if struct_name == "Guid":
        return r.take(16).hex()
    if struct_name in ("Vector", "Rotator"):
        return [f32(r.unpack("<f")) for _ in range(3)]
    if struct_name in ("Vector2D",):
        return [f32(r.unpack("<f")) for _ in range(2)]
    if struct_name in ("LinearColor", "Quat", "Vector4"):
        return [f32(r.unpack("<f")) for _ in range(4)]
    if struct_name == "Color":
        return list(r.take(4))
    if struct_name in ("IntPoint",):
        return [r.i32(), r.i32()]
    if struct_name in ("DateTime", "Timespan"):
        return r.unpack("<q")
    if struct_name in ("SoftObjectPath", "SoftClassPath"):
        path = r.name()
        r.string()
        return "." + path
    if struct_name == "GameplayTagContainer":
        return [r.name() for _ in range(r.i32())]
    return props(r)


def value(r, typ, tag, size):
    if typ == "BoolProperty":
        return tag["bool"]
    if typ == "ByteProperty":
        return r.take(1)[0] if tag["enum"] == "None" else r.name()
    if typ == "StructProperty":
        return struct_value(r, tag["struct"])
    if typ in ("ArrayProperty", "SetProperty"):
        inner = tag["inner"]
        if typ == "SetProperty":
            for _ in range(r.i32()):  # elements to remove
                element(r, inner)
        n = r.i32()
        if inner == "StructProperty" and typ == "ArrayProperty":
            r.name(); r.name(); r.i32(); r.i32()  # inner tag: name, type, size, array index
            struct_name = r.name()
            r.take(16)
            if r.take(1)[0]:
                r.take(16)
            return [struct_value(r, struct_name) for _ in range(n)]
        elem_size = (size - 4) // n if n and inner == "ByteProperty" else None
        return [element(r, inner, elem_size) for _ in range(n)]
    if typ == "MapProperty":
        for _ in range(r.i32()):  # keys to remove
            element(r, tag["inner"])
        return [{"k": element(r, tag["inner"]), "v": element(r, tag["value"])} for _ in range(r.i32())]
    return element(r, typ)


def props(r):
    out = {}
    while True:
        name = r.name()
        if name == "None":
            return out
        typ, size = r.name(), r.i32()
        r.i32()  # array index
        tag = {}
        if typ == "StructProperty":
            tag["struct"] = r.name()
            r.take(16)
        elif typ == "BoolProperty":
            tag["bool"] = r.take(1)[0] != 0
        elif typ in ("ByteProperty", "EnumProperty"):
            tag["enum"] = r.name()
        elif typ in ("ArrayProperty", "SetProperty"):
            tag["inner"] = r.name()
        elif typ == "MapProperty":
            tag["inner"], tag["value"] = r.name(), r.name()
        if r.take(1)[0]:
            r.take(16)  # property guid
        start = r.p
        out[clean_name(name)] = value(r, typ, tag, size)
        r.p = start + size  # stay aligned even if a value was only partly understood


def read_table(uasset, uexp):
    """Rows of a DataTable package as {RowName: {Field: value}}, or None if it is not a DataTable."""
    h = Reader(uasset)
    if h.unpack("<I") != 0x9E2A83C1:
        raise ValueError("not a UE package")
    legacy = h.i32()
    if legacy != -4:
        h.i32()  # legacy UE3 version
    h.i32(); h.i32()  # UE4 version, licensee version
    h.take(h.i32() * 20)  # custom versions
    header_size = h.i32()
    h.string()  # folder name
    flags = h.unpack("<I")
    name_count, name_offset = h.i32(), h.i32()
    if not flags & 0x80000000:
        h.string()  # localization id (uncooked packages only)
    h.i32(); h.i32()  # gatherable text data
    export_count, export_offset = h.i32(), h.i32()
    import_count, import_offset = h.i32(), h.i32()

    h.p, names = name_offset, []
    for _ in range(name_count):
        names.append(h.string())
        h.take(4)  # hashes
    h.names = names
    h.p, imports = import_offset, []
    for _ in range(import_count):
        h.name(); h.name(); h.i32()  # class package, class name, outer
        imports.append(h.name())
    h.p = export_offset
    class_index = h.i32()
    h.i32(); h.i32(); h.i32(); h.name(); h.i32()  # super, template, outer, object name, flags
    size, offset = h.unpack("<q"), h.unpack("<q")
    if class_index >= 0 or imports[-class_index - 1] not in ("DataTable", "CompositeDataTable"):
        return None

    r = Reader(uexp[offset - header_size:offset - header_size + size], names, imports)
    props(r)  # the table's own properties (RowStruct ...)
    r.i32()  # object guid flag
    return {r.name(): props(r) for _ in range(r.i32())}


def main():
    pak = game_dir() / PAK_REL
    if not pak.exists():
        sys.exit(f"找不到 {pak}")
    exe = repak()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=HOME) as tmp:
        subprocess.run([str(exe), "unpack", "-q", "-i", TABLES_IN_PAK, "-o", tmp, str(pak)], check=True)
        src = Path(tmp) / TABLES_IN_PAK
        done, failed = 0, []
        for ua in sorted(src.glob("*.uasset")):
            try:
                rows = read_table(ua.read_bytes(), ua.with_suffix(".uexp").read_bytes())
            except (ValueError, EOFError, IndexError, KeyError):
                failed.append(ua.stem)  # so far only UI text-style tables (custom font structs)
                continue
            if rows is None:
                continue
            with open(DATA_DIR / f"{ua.stem}.json", "w", encoding="utf-8") as f:
                json.dump(rows, f, ensure_ascii=False, indent=1)
            done += 1
    print(f"已导出 {done} 张表到 {DATA_DIR}；跳过 {len(failed)} 张解析不了的表")
    missing = [t for t in REQUIRED if not (DATA_DIR / f"{t}.json").exists()]
    if missing:
        sys.exit("陪玩需要的表没导出来：" + "、".join(missing))
    print("陪玩需要的表都齐了。")


if __name__ == "__main__":
    main()
