# Импорт библиотек
import os
import subprocess
import json
import sys
import requests
from pathlib import Path
from datetime import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator, ShortCircuitOperator
from airflow.operators.email import EmailOperator

# Переменные окружения
MODEL_PATH = Path('models/model.pkl')
MODEL_VERSION = os.getenv('MODEL_VERSION', 'v1.0.0')
METRIC_THRESHOLD = float(os.getenv('METRIC_THRESHOLD', '0.9'))
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# Обучение модели
def train_model(ti):
    result = subprocess.run(
        [sys.executable, 'src/train.py'],
        capture_output=True,
        text=True,
        check=True
    )

    metrics = json.loads(result.stdout.strip().splitlines()[-1])
    ti.xcom_push(key='metric', value=metrics['f1_weighted'])

    print('Обучение завершено')

# Оценка модели
def evaluate_model(ti):
    f1_score = ti.xcom_pull(key='metric', task_ids='train_model')
    print(f'Средневзвешенная F1-score равна: {f1_score}')

# Принятие решения о деплое модели на основе превышения baseline
def deploy_model(ti):
    f1_score = float(ti.xcom_pull(key='metric', task_ids='train_model'))
    deploy_flag = f1_score > METRIC_THRESHOLD

    if not deploy_flag:
        if MODEL_PATH.exists():
            MODEL_PATH.unlink()

    print(f'Решение о деплое в прод. F1-score равна: {f1_score}, baseline равен: {METRIC_THRESHOLD}, решение: {deploy_flag}')
    return deploy_flag

# Отправка уведомления в Telegram
def notify_telegram(ti):
    f1_score = ti.xcom_pull(key='metric', task_ids='train_model')

    text = (f'Модель ML выведена в прод. Версия: {MODEL_VERSION}, Средневзвешенная F1-score: {f1_score}, Baseline: {METRIC_THRESHOLD}')

    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
    resp = requests.post(url, json={'chat_id': TELEGRAM_CHAT_ID, 'text': text})
    resp.raise_for_status()

    print('Уведомление отправлено в Telegram')

with DAG(
    'ml_retrain_pipeline',
    start_date=datetime(2025, 12, 25),
    schedule="@daily",
    catchup=False,
    tags=['mlops', 'retrain']
) as dag:

    train = PythonOperator(task_id='train_model', python_callable=train_model)
    evaluate = PythonOperator(task_id='evaluate_model', python_callable=evaluate_model)
    deploy = ShortCircuitOperator(task_id='deploy_model', python_callable=deploy_model)
    notify = PythonOperator(task_id='notify_success', python_callable=notify_telegram)

    train >> evaluate >> deploy >> notify