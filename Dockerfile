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
COPY models/general_v1 ./models/general_v1
COPY models/station_2402 ./models/station_2402
COPY models/station_2351 ./models/station_2351
COPY reports/general_v1/training.json ./reports/general_v1/training.json
COPY reports/station_2402/resultados.json ./reports/station_2402/resultados.json
COPY reports/station_2351/resultados.json ./reports/station_2351/resultados.json
COPY data/processed/oefa_daily.csv ./data/processed/oefa_daily.csv
COPY data/processed/station_2402_hourly.csv ./data/processed/station_2402_hourly.csv
COPY data/processed/station_2351_hourly.csv ./data/processed/station_2351_hourly.csv
COPY models/puno_experimental ./models/puno_experimental
COPY data/processed/puno_forecasts.json ./data/processed/puno_forecasts.json
RUN pip install --no-cache-dir --no-deps . && useradd --create-home appuser && chown -R appuser:appuser /app
ARG APP_COMMIT=local
ENV AIRPREDICT_ROOT=/var/data AIRPREDICT_SEED=/app AIRPREDICT_HOST=0.0.0.0 PORT=8000 APP_COMMIT=$APP_COMMIT
EXPOSE 8000
CMD ["python", "-m", "airepredict.boot"]
