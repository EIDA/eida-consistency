# Global EIDA Consistency Summary

## Per-node summary

| Node | Epochs Requested | Epochs Usable | Total Checks | Consistent | Inconsistent | Score |
|------|------------------|---------------|--------------|------------|--------------|-------|
| BGR | 20 | 20 | 20 | 15 | 5 | 75.0 % |
| BGS | 20 | 11 | 11 | 6 | 5 | 54.55 % |
| ETH | 20 | 20 | 20 | 19 | 1 | 95.0 % |
| GEOFON | 20 | 20 | 20 | 20 | 0 | 100.0 % |
| KOERI | 20 | 20 | 20 | 10 | 10 | 50.0 % |
| LMU | 20 | 20 | 20 | 20 | 0 | 100.0 % |
| NIEP | 20 | 20 | 20 | 15 | 5 | 75.0 % |
| NOA | 20 | 20 | 20 | 16 | 4 | 80.0 % |
| RESIF | 20 | 20 | 20 | 20 | 0 | 100.0 % |
| UIB-NORSAR | 20 | 20 | 20 | 18 | 2 | 90.0 % |

---

## Node: BGR

- Seed: `214412`
- Epochs requested: `20`
- Epochs usable: `20`
- Candidate pool: `100`
- Queries performed: `29`
- Total checks: `20`
- Consistent: `15`
- Inconsistent: `5`
- Score: **75.0 %**

### Reproduce
```bash
uv run eida-consistency consistency --node BGR --epochs 20
```

### Explore inconsistencies
```bash
uv run eida-consistency explore reports/nodes/bgr/*.json
```

---

## Node: BGS

- Seed: `173308`
- Epochs requested: `20`
- Epochs usable: `11`
- Candidate pool: `100`
- Queries performed: `400`
- Total checks: `11`
- Consistent: `6`
- Inconsistent: `5`
- Score: **54.55 %**

### Reproduce
```bash
uv run eida-consistency consistency --node BGS --epochs 20
```

### Explore inconsistencies
```bash
uv run eida-consistency explore reports/nodes/bgs/*.json
```

---

## Node: ETH

- Seed: `332194`
- Epochs requested: `20`
- Epochs usable: `20`
- Candidate pool: `100`
- Queries performed: `193`
- Total checks: `20`
- Consistent: `19`
- Inconsistent: `1`
- Score: **95.0 %**

### Reproduce
```bash
uv run eida-consistency consistency --node ETH --epochs 20
```

### Explore inconsistencies
```bash
uv run eida-consistency explore reports/nodes/eth/*.json
```

---

## Node: GEOFON

- Seed: `193844`
- Epochs requested: `20`
- Epochs usable: `20`
- Candidate pool: `100`
- Queries performed: `30`
- Total checks: `20`
- Consistent: `20`
- Inconsistent: `0`
- Score: **100.0 %**

### Reproduce
```bash
uv run eida-consistency consistency --node GEOFON --epochs 20
```

### Explore inconsistencies
```bash
uv run eida-consistency explore reports/nodes/geofon/*.json
```

---

## Node: KOERI

- Seed: `859306`
- Epochs requested: `20`
- Epochs usable: `20`
- Candidate pool: `100`
- Queries performed: `30`
- Total checks: `20`
- Consistent: `10`
- Inconsistent: `10`
- Score: **50.0 %**

### Reproduce
```bash
uv run eida-consistency consistency --node KOERI --epochs 20
```

### Explore inconsistencies
```bash
uv run eida-consistency explore reports/nodes/koeri/*.json
```

---

## Node: LMU

- Seed: `674788`
- Epochs requested: `20`
- Epochs usable: `20`
- Candidate pool: `100`
- Queries performed: `37`
- Total checks: `20`
- Consistent: `20`
- Inconsistent: `0`
- Score: **100.0 %**

### Reproduce
```bash
uv run eida-consistency consistency --node LMU --epochs 20
```

### Explore inconsistencies
```bash
uv run eida-consistency explore reports/nodes/lmu/*.json
```

---

## Node: NIEP

- Seed: `330643`
- Epochs requested: `20`
- Epochs usable: `20`
- Candidate pool: `100`
- Queries performed: `48`
- Total checks: `20`
- Consistent: `15`
- Inconsistent: `5`
- Score: **75.0 %**

### Reproduce
```bash
uv run eida-consistency consistency --node NIEP --epochs 20
```

### Explore inconsistencies
```bash
uv run eida-consistency explore reports/nodes/niep/*.json
```

---

## Node: NOA

- Seed: `596334`
- Epochs requested: `20`
- Epochs usable: `20`
- Candidate pool: `100`
- Queries performed: `32`
- Total checks: `20`
- Consistent: `16`
- Inconsistent: `4`
- Score: **80.0 %**

### Reproduce
```bash
uv run eida-consistency consistency --node NOA --epochs 20
```

### Explore inconsistencies
```bash
uv run eida-consistency explore reports/nodes/noa/*.json
```

---

## Node: RESIF

- Seed: `478857`
- Epochs requested: `20`
- Epochs usable: `20`
- Candidate pool: `100`
- Queries performed: `23`
- Total checks: `20`
- Consistent: `20`
- Inconsistent: `0`
- Score: **100.0 %**

### Reproduce
```bash
uv run eida-consistency consistency --node RESIF --epochs 20
```

### Explore inconsistencies
```bash
uv run eida-consistency explore reports/nodes/resif/*.json
```

---

## Node: UIB-NORSAR

- Seed: `493182`
- Epochs requested: `20`
- Epochs usable: `20`
- Candidate pool: `100`
- Queries performed: `78`
- Total checks: `20`
- Consistent: `18`
- Inconsistent: `2`
- Score: **90.0 %**

### Reproduce
```bash
uv run eida-consistency consistency --node UIB-NORSAR --epochs 20
```

### Explore inconsistencies
```bash
uv run eida-consistency explore reports/nodes/uib-norsar/*.json
```

---
