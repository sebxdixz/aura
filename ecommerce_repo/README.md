# Sample E-commerce Codebase for RAG

This folder simulates a medium-complexity e-commerce repository for hackathon demos.

The API indexes this tree into PostgreSQL + pgvector at startup when:

- `RAG_AUTO_INDEX=true`
- `ECOMMERCE_CODEBASE_PATH=/workspace/ecommerce_repo` (default in docker-compose)

You can replace this folder with a real open-source e-commerce repository while keeping the same mount path.

