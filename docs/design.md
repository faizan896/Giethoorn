# A sense of place

Giethoorn's interface takes its colour and character from the village photograph
provided by the product owner: shaded trees along a canal, warm brick cottages,
thatched roofs, ivory window frames and quiet water. These are interpreted visual
references, rather than measured samples from the original image.

The interface uses those materials with restraint. A forest green navigation
frame surrounds warm, light data surfaces. Serif headings and a small bridge over
water give the brand a connection to the village. Account values, prices and
operational states retain clear, tabular sans-serif or monospace typography.
The photograph is a reference, not a background behind financial data.

| Material | Colour | Interface role |
| --- | --- | --- |
| Tree shade | `#263C30` | Navigation, primary actions, dark ink |
| Canal foliage | `#526B49` | Quote series, positive states, progress |
| Warm window frames | `#FFFEF9` | Cards and header |
| Pale sky and stone | `#F5F3EC` | Page canvas |
| Cottage brick | `#9C6B51` | Depth series and accents; darker `#82543D` for text |
| Thatched roof | `#B99B63` | Decorative trim; darker `#85652B` for warning text |
| Garden sage | `#EAF0E4` | Positive state backgrounds |

The source of truth is [theme.css](../web/theme.css). The monitor and Paper Lab
embed it when rendering, so saved HTML remains self-contained and works offline.
Fonts use local system stacks; the design requires no font service or CDN.

Colour always accompanies words, shapes or line patterns. Depth uses a dashed
brick line, quotes a solid moss line. Fresh, stale, historical, synthetic and
pending states keep explicit labels. Keyboard focus is visible; small text uses
the darker grey-green token rather than pale decorative colours. The narrow
layout keeps charts responsive and tables scroll within their own panels.

This visual layer does not change market observations, freshness rules, replay
verification, paper accounting, assumptions or evidence. Synthetic Paper Lab
results remain explicitly synthetic. Saved monitor views remain timestamped
snapshots rather than live data.
