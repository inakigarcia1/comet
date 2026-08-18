# Comet — Filtros avanzados y Torrents Manuales

Extiende la configuracion base64 y expone una API admin para insercion manual de torrents.

## Nuevos campos de configuracion

Todos en `ConfigModel`. Defaults inactivos (`0` o `[]`). Compatibilidad 100% con configs legacy.

| Campo | Tipo | Default | Notas |
|---|---|---|---|
| `maxSizeMovie` | float (bytes) | `0` | Override de tamano maximo para movies. `0` → fallback `maxSize`. |
| `maxSizeSeries` | float (bytes) | `0` | Override de tamano maximo para series. `0` → fallback `maxSize`. |
| `minBitrateMbps` | float | `0` | Bitrate minimo en Mbps. `0` = desactivado. Solo aplica si el request envia `?durationMinutes`. |
| `maxBitrateMbps` | float | `0` | Bitrate maximo en Mbps. `0` = desactivado. Validado: `maxBitrateMbps >= minBitrateMbps`. |
| `filenameInclude` | list[str] | `[]` | Substrings case-insensitive. Vacio = acepta cualquier filename. |
| `filenameExclude` | list[str] | `[]` | Substrings case-insensitive. Gana sobre `include`. |
| `releaseTypesAllowlist` | list[str] | `[]` | Categorias RTN permitidas. Vacio = todas las no-bloqueadas. |
| `releaseTypesBlocklist` | list[str] | `[]` | Categorias RTN bloqueadas. Gana sobre allowlist. |

### Taxonomia de release types

Unica fuente en `comet/utils/release_types.py`. Reutiliza `parsed.rip` de RTN sin regex propias.

```
remux, bluray, web, webdl, webmux, hdtv, dvd,
bdrip, brrip, dvdrip, hdrip, webrip, webdlrip, tvrip,
cam, screener, telecine, telesync, unknown
```

### Orden de filtros

```
parse -> title/year/adult -> user_filters ->
  - max size (per-tipo)
  - filename include/exclude
  - release type allow/block
  - bitrate (cuando hay durationMinutes)
rank_torrents (RTN) -> cache ->
_select_info_hashes_by_resolution (maxResultsPerResolution, ultimo)
```

`maxResultsPerResolution` se aplica al final, despues de todos los demas filtros.

## Query param: `durationMinutes`

```
GET /<b64>/stream/movie/tt0111161.json?durationMinutes=142
GET /<b64>/stream/series/tt1234567:1:4.json?durationMinutes=44
```

- Activa el filtro de bitrate.
- Fuerza `CachePolicies.no_cache()` cuando hay filtros de bitrate configurados.
- Season packs / multipacks se excluyen del calculo (no se pueden atribuir a un episodio puntual).

## Endpoints del Admin API

Todos requieren `require_admin_auth` (cookie `admin_session`).

### POST /admin/api/torrents/manual

Crea o hace upsert de un torrent manual.

```json
{
  "mediaId": "tt0111161",
  "mediaType": "movie",
  "infoHash": "0123456789abcdef0123456789abcdef01234567",
  "title": "Movie.Name.2025.2160p.UHD.BluRay.REMUX-GROUP",
  "size": 75161927680,
  "seeders": 10,
  "fileIndex": null,
  "tracker": "Manual",
  "sources": ["udp://tracker.example.com:1337"],
  "shareCometnet": false
}
```

Tambien acepta `magnet` en vez de `infoHash`+`title`; se extraen `btih`, `dn`, `tr` del magnet. Sin descargar `.torrent`.

Respuesta `200`:

```json
{"success": true, "mediaId": "tt0111161", "infoHash": "...", "shareCometnet": false}
```

Errores:
- `422` si RTN no parsea el title.
- `422` si el hash no es 40 hex chars.

### POST /admin/api/torrents/manual/bulk

Hasta 500 torrents en un request. Cada item se valida independientemente. Las entradas invalidas se reportan en `rejected` con el indice original.

```json
{
  "torrents": [
    {"mediaId": "tt0111161", "mediaType": "movie", "infoHash": "...", "title": "..."},
    {"mediaId": "tt0111161", "mediaType": "movie", "infoHash": "...", "title": "..."}
  ]
}
```

Respuesta:

```json
{"success": true, "total": 2, "inserted": 2, "rejected": []}
```

### GET /admin/api/torrents/manual

Lista torrents manuales. Filtros opcionales: `media_id`, `info_hash`, `limit` (default 50, max 200), `offset` (default 0).

```
GET /admin/api/torrents/manual?media_id=tt0111161&limit=20
```

```json
{
  "torrents": [
    {
      "mediaId": "tt0111161",
      "infoHash": "0123456789abcdef0123456789abcdef01234567",
      "title": "...",
      "season": null,
      "episode": null,
      "fileIndex": null,
      "size": 75161927680,
      "seeders": 10,
      "tracker": "Manual",
      "updatedAt": 1755520000.0,
      "shareCometnet": false
    }
  ],
  "count": 1
}
```

### DELETE /admin/api/torrents/manual

Borra un torrent manual por scope. No afecta torrents no-manuales bajo el mismo scope.

```json
{
  "mediaId": "tt0111161",
  "infoHash": "0123456789abcdef0123456789abcdef01234567",
  "season": null,
  "episode": null
}
```

Respuesta:

```json
{"success": true, "deleted": 1}
```

## Persistencia y semantica

- **Manual torrents**: flag `is_manual=1` + `manual_share_cometnet=0` por default.
- **TTL**: `_run_startup_cleanup` excluye `is_manual=1` del DELETE por `updated_at`. Un manual sobrevive aunque pase el TTL.
- **CometNet**: manuales NO se difunden por default. Solo si `shareCometnet=true` en el payload. Cero colision con flags existentes.
- **Scraper posterior**: si un scraper re-encuentra el mismo `(media_id, info_hash, season_norm, episode_norm)`, su upsert NO toca `is_manual`. La marca se preserva.
- **Refresh live acotado**: si `filenameInclude` no matchea ningun torrent cacheado, una sola pasada de scrape se fuerza (lock distribuido de Comet existente evita loops).
