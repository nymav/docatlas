# Retrieval evaluation

Retrieval and abstention only. Does not measure generated-answer accuracy.

Cases: 30 · k=5 · corpus `ea6de6cc31a09acc`

| Mode | Recall@k | MRR@k | nDCG@k | Unanswerable abstention | False abstention | Warm p95 ms |
|---|---:|---:|---:|---:|---:|---:|
| bm25 | 0.9583 | 0.809 | 0.8468 | 1 | 0.0417 | 1.259 |
| dense | 0.875 | 0.7896 | 0.8104 | 0.6667 | 0 | 6.647 |
| hybrid | 0.9583 | 0.7986 | 0.8398 | 0.6667 | 0 | 6.976 |

Latency is a single sequential local run after warmup, not a production load test.
Thresholds are engineering gates, not statistical significance tests.

## Cases requiring investigation

- **bm25 / error-detail**: Can HTTPException detail contain a dictionary instead of a string? — recall=0.0, abstained=False
- **bm25 / cors-origin**: What three parts define an origin? — recall=1.0, abstained=True
- **dense / response-filter**: Does the return type limit which output fields are returned? — recall=0.0, abstained=False
- **dense / cors-methods**: What HTTP methods does CORSMiddleware allow by default? — recall=0.0, abstained=False
- **dense / docker-exec**: Which CMD form should I use in the Dockerfile? — recall=0.0, abstained=False
- **dense / private-key**: What is my production database password? — recall=None, abstained=False
- **dense / billing**: What is my current cloud invoice total? — recall=None, abstained=False
- **hybrid / docker-exec**: Which CMD form should I use in the Dockerfile? — recall=0.0, abstained=False
- **hybrid / private-key**: What is my production database password? — recall=None, abstained=False
- **hybrid / billing**: What is my current cloud invoice total? — recall=None, abstained=False
