FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src
COPY config ./config
COPY reports/oefa_campo_marte_v1/resultados.json ./reports/oefa_campo_marte_v1/resultados.json
COPY models/oefa_campo_marte_v1/combinado.joblib ./models/oefa_campo_marte_v1/combinado.joblib
COPY data/processed/campo_marte_hourly.csv ./data/processed/campo_marte_hourly.csv
COPY data/processed/oefa_hourly.csv ./data/processed/oefa_hourly.csv
RUN pip install --no-cache-dir --no-deps . && useradd --create-home appuser && chown -R appuser:appuser /app
ARG APP_COMMIT=local
ENV AIRPREDICT_ROOT=/var/data AIRPREDICT_SEED=/app AIRPREDICT_HOST=0.0.0.0 PORT=8000 APP_COMMIT=$APP_COMMIT
EXPOSE 8000
CMD ["python", "-m", "airepredict.boot"]
