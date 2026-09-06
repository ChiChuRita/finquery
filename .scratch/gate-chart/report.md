# Gate report

10 of 12 candidates kept (83 %), 2 dropped.

| household | rows | share |
| --- | ---: | ---: |
| couple | 3 | 30 % |
| family | 2 | 20 % |
| pensioner | 2 | 20 % |
| student | 2 | 20 % |
| freelancer | 1 | 10 % |

| kind | rows | share |
| --- | ---: | ---: |
| area | 2 | 20 % |
| line | 2 | 20 % |
| bar | 1 | 10 % |
| bar_grouped | 1 | 10 % |
| bar_horizontal | 1 | 10 % |
| bar_stacked | 1 | 10 % |
| doughnut | 1 | 10 % |
| sankey | 1 | 10 % |

| language | rows | share |
| --- | ---: | ---: |
| en | 6 | 60 % |
| de | 4 | 40 % |

| difficulty | rows | share |
| --- | ---: | ---: |
| 2 | 5 | 50 % |
| 3 | 5 | 50 % |

## Why the rest was dropped

| reason | rows | share |
| --- | ---: | ---: |
| self-check-failed | 2 | 100 % |

One line per drop:

- `smoke-w04-student-line-no-grid-en` the self-check found something on the first attempt: Every chart carries `tooltip: { use: tooltip, format: ... }`.; Set `grid: true` on `scales.y`, the euro axis.; The euro axis needs `axis: { ticks: { format: eurShort } }` on `scales.y`.; The euro axis has to start at zero, or a change of a few percent is drawn as a cliff. Give `scales.y` the domain `scale: s
- `smoke-w05-student-doughnut-no-legend-de` the self-check found something on the first attempt: More than one series needs a legend: `color: { legend: colorLegend({ placement: 'bottom' }) }`.
