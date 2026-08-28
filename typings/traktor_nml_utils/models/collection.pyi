from __future__ import annotations

class Infotype:
    playtime: int | None
    def __init__(self, playtime: int | None = None) -> None: ...

class Primarykeytype:
    key: str | None
    type: str | None
    def __init__(
        self,
        value: str | None = None,
        type: str | None = None,
        key: str | None = None,
    ) -> None: ...

class Locationtype:
    dir: str | None
    file: str | None
    volume: str | None
    def __init__(
        self,
        dir: str | None = None,
        file: str | None = None,
        volume: str | None = None,
        volumeid: str | None = None,
    ) -> None: ...

class Entrytype:
    primarykey: Primarykeytype | None
    location: Locationtype | None
    title: str | None
    artist: str | None
    info: Infotype | None
    def __init__(
        self,
        location: Locationtype | None = None,
        album: object | None = None,
        modification_info: object | None = None,
        info: Infotype | None = None,
        tempo: object | None = None,
        loudness: object | None = None,
        musical_key: object | None = None,
        loopinfo: object | None = None,
        cue_v2: list[object] | None = None,
        stems: object | None = None,
        primarykey: Primarykeytype | None = None,
        modified_date: str | None = None,
        modified_time: int | None = None,
        lock: int | None = None,
        lock_modification_time: str | None = None,
        audio_id: str | None = None,
        title: str | None = None,
        artist: str | None = None,
    ) -> None: ...

class Playlisttype:
    entry: list[Entrytype]
    entries: int | None
    type: str | None
    uuid: str | None
    def __init__(
        self,
        content: object | None = None,
        entry: list[Entrytype] | None = None,
        entries: int | None = None,
        type: str | None = None,
        uuid: str | None = None,
    ) -> None: ...

class Smartlisttype: ...

class Nodetype:
    playlist: Playlisttype | None
    subnodes: Subnodestype | None
    type: str | None
    name: str | None
    smartplaylist: Smartlisttype | None
    def __init__(
        self,
        playlist: Playlisttype | None = None,
        subnodes: Subnodestype | None = None,
        type: str | None = None,
        name: str | None = None,
        smartplaylist: Smartlisttype | None = None,
    ) -> None: ...

class Subnodestype:
    node: list[Nodetype]
    count: int | None
    def __init__(
        self,
        node: list[Nodetype] | None = None,
        count: int | None = None,
    ) -> None: ...

class Playliststype:
    node: Nodetype | None

class Collectiontype:
    entry: list[Entrytype]
    entries: int | None

class Nml:
    playlists: Playliststype | None
    collection: Collectiontype | None
