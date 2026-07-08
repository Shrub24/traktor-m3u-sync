class Infotype:
    playtime: int | None

class Primarykeytype:
    key: str | None

class Locationtype:
    dir: str | None
    file: str | None
    volume: str | None

class Entrytype:
    primarykey: Primarykeytype | None
    location: Locationtype | None
    title: str | None
    artist: str | None
    info: Infotype | None

class Playlisttype:
    entry: list[Entrytype]

class Smartlisttype: ...

class Nodetype:
    playlist: Playlisttype | None
    subnodes: "Subnodestype | None"
    type: str | None
    name: str | None
    smartplaylist: Smartlisttype | None

class Subnodestype:
    node: list[Nodetype]

class Playliststype:
    node: Nodetype | None

class Nml:
    playlists: Playliststype | None
