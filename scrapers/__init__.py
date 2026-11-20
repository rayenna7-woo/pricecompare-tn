from . import spacenet, tunisianet, zoom

# Every store module has the same interface: STORE (name) and search(query).
ALL_SCRAPERS = [tunisianet, zoom, spacenet]
