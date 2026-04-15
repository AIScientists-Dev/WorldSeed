# Source Catalog

This skill supports only the sources below.

Default sources:
- `met`
- `openverse`
- `aic`
- `cleveland`
- `vam`
- `wellcome`
- `ycba`

Optional sources:
- `wikimedia`
- `walters`
- `nasa`

Use the default set first. The AI should choose sources per entity, not run every source for every entity by default.

## Capability Map

Use this table to choose sources instead of hardcoding one global order.

| Source | Speed | Best roles | Best first use | Widen when | Common trap |
|---|---|---|---|---|---|
| `openverse` | Fast | `zone`, `agent`, `item`, `symbolic` | broad first-pass recall | keep when you need more breadth or symbolic coverage | metadata noise, homonyms |
| `aic` | Fast | `zone`, `item` | formal historical interiors and objects | use when broad recall is too noisy | title/artist coincidences |
| `cleveland` | Fast | `zone`, `item`, `symbolic` | short noun-heavy museum queries | use when you want cleaner museum objects | weaker on long descriptive queries |
| `vam` | Medium | `zone`, `item` | design-heavy rooms and decorative material | use when interiors need more refinement | signage/text-card results |
| `wellcome` | Medium | `agent`, `item`, `symbolic` | portraits, paper, science-adjacent imagery | use when people/paper motifs are missing | weak on large rooms |
| `ycba` | Medium | `zone`, `item`, `symbolic` | interiors, conservatories, prints | use when you want a more historical/print-heavy alternative | HTML parsing path is more brittle |
| `met` | Slow | `zone`, `agent`, `item`, `symbolic` | high-quality fallback after narrower passes | use when earlier sources are weak but quality matters | hydration cost is high |
| `wikimedia` | Medium | `symbolic`, `agent` | named motifs, famous works, known figures | use for motif catch-up or coverage gaps | scans, covers, filename overclaim |
| `walters` | Medium | `item`, `agent` | watches, keys, manuscript-adjacent objects | use when object-specific museum results matter | occasional brittle access / `403` |
| `nasa` | Fast | `symbolic`, `zone` | celestial and scientific imagery | use only when the scene really wants cosmic material | too literal for non-scientific scenes |

## Fast Default Strategy

- `zone`: `openverse` -> `aic` or `cleveland` -> `vam` or `ycba` -> `met`
- `agent`: `openverse` -> `wellcome` -> `aic` or `ycba` -> `met`
- `item`: `openverse` -> `aic` or `cleveland` -> `walters` when justified -> `met`
- `symbolic`: `openverse` -> `wikimedia` for motifs -> `nasa` for celestial/scientific cases

This is guidance, not a fixed route. If the first source produces clearly good candidates, stop early.

## Default Sources

### `met`

- Best for: interiors, objects, portraits, symbolic historical material
- Endpoint: `GET /search`, then `GET /objects/{id}`
- Example:

```bash
curl -sS 'https://collectionapi.metmuseum.org/public/collection/v1/search?hasImages=true&q=salon'
```

- Returns: JSON search IDs, then JSON object detail records
- Download: yes, review-size jpg from `primaryImageSmall`
- Trap: strong source, but slow because object hydration is required; better as a later pass than as the first source call

### `openverse`

- Best for: broad recall, fallback coverage, symbolic and object catch-up
- Endpoint: `GET https://api.openverse.org/v1/images/`
- Example:

```bash
curl -sS 'https://api.openverse.org/v1/images/?q=sealed%20letter&page_size=8'
```

- Returns: JSON `results[]`
- Download: usually yes via direct image or thumbnail URLs
- Trap: good breadth, but metadata traps are common
- Trap: short symbolic queries can return homonym results; visually verify before ranking top picks
- Practical note: this is the fastest default first-pass source for a brand-new scene

### `aic`

- Best for: interiors, objects, formal historical imagery
- Endpoint: `GET https://api.artic.edu/api/v1/artworks/search`
- Example:

```bash
curl -sS 'https://api.artic.edu/api/v1/artworks/search?q=interior&query[term][is_public_domain]=true&fields=id,title,artist_display,date_display,image_id&limit=8'
```

- Returns: JSON `data[]`
- Download: yes, IIIF jpg derived from `image_id`
- Trap: artist-name/title coincidences can produce false positives

### `cleveland`

- Best for: rooms, moths, decorative objects, simple museum queries
- Endpoint: `GET https://openaccess-api.clevelandart.org/api/artworks/`
- Example:

```bash
curl -sS 'https://openaccess-api.clevelandart.org/api/artworks/?q=conservatory&has_image=1&limit=8'
```

- Returns: JSON `data[]`
- Download: yes, image URLs are exposed directly
- Trap: prefers short noun-heavy queries

### `vam`

- Best for: rooms, conservatories, design objects, refined decorative material
- Endpoint: `GET https://api.vam.ac.uk/v2/objects/search`
- Example:

```bash
curl -sS 'https://api.vam.ac.uk/v2/objects/search?q=conservatory&images_exist=1&page_size=8'
```

- Returns: JSON `records[]`
- Download: yes, IIIF jpg from the image base URL
- Trap: text-card and signage-like results appear

### `wellcome`

- Best for: portraits, letters, paper, medicine, science motifs
- Endpoint: `GET https://api.wellcomecollection.org/catalogue/v2/images`
- Example:

```bash
curl -sS 'https://api.wellcomecollection.org/catalogue/v2/images?query=astronomer&pageSize=8'
```

- Returns: JSON `results[]`
- Download: yes, IIIF jpg constructed from thumbnail info
- Trap: weak for rooms and large environment entities

### `ycba`

- Best for: interiors, conservatories, astronomy prints, archival paper material
- Endpoint: `GET https://collections.britishart.yale.edu/?q=...`
- Example:

```bash
curl -sS 'https://collections.britishart.yale.edu/?q=conservatory'
```

- Returns: HTML search page with result cards
- Download: yes, review-size thumbnails can be downloaded
- Trap: current stable path is page parsing via `curl`, not the original Python HTTP client

## Optional Sources

### `wikimedia`

- Use when: named motifs, famous works, known figures, or default coverage is weak
- Endpoint: MediaWiki API search plus file detail lookup
- Example:

```bash
curl -sS 'https://commons.wikimedia.org/w/api.php?action=query&list=search&srsearch=eclipse&srnamespace=6&format=json&srlimit=8&origin=*'
```

- Returns: JSON search results, then per-file detail JSON
- Download: yes, but file type varies by item
- Trap: many scans, book covers, and low-value reproductions
- Trap: file titles often overstate relevance; short symbolic tokens can collide with person names and event photos

### `walters`

- Use when: keys, watches, portraits, manuscript-adjacent objects
- Endpoint: `GET https://art.thewalters.org/search/?q=...`
- Example:

```bash
curl -sS 'https://art.thewalters.org/search/?q=pocket%20watch'
```

- Returns: HTML search page with result cards
- Download: yes, thumbnail jpgs are directly available
- Trap: narrower than the stronger default sources
- Trap: page access can be brittle; if it returns `403` or empty cards, widen to another object-friendly source instead of retrying blindly

### `nasa`

- Use when: eclipse, comet, observatory, celestial, scientific atmosphere
- Endpoint: `GET https://images-api.nasa.gov/search`
- Example:

```bash
curl -sS 'https://images-api.nasa.gov/search?q=solar%20eclipse&media_type=image'
```

- Returns: JSON `collection.items[]`
- Download: yes, thumbnail and larger image links are available
- Trap: not for general historical scenes; use only for cosmic/scientific entities
