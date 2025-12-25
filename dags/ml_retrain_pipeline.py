import os
import subprocess
import json
import sys
from pathlib import Path
from datetime import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator, ShortCircuitOperator
from airflow.operators.email import EmailOperator

MODEL_PATH = Path('models/model.pkl')
MODEL_VERSION = os.getenv('MODEL_VERSION', 'v1.0.0')
METRIC_THRESHOLD = float(os.getenv('METRIC_THRESHOLD', '0.9'))
EMAIL_ADDRESS = os.getenv('EMAIL_ADDRESS', 'mozhogin.ss@phystech.edu')

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

def evaluate_model(ti):
    f1_score = ti.xcom_pull(key='metric', task_ids='train_model')
    print(f'Средневзвешенный F1-score равен: {f1_score}')

def deploy_model(ti):
    f1_score = float(ti.xcom_pull(key='metric', task_ids='train_model'))
    deploy_flag = f1_score > METRIC_THRESHOLD

    if not deploy_flag:
        if MODEL_PATH.exists():
            MODEL_PATH.unlink()

    print(f'Решение о деплое в прод. F1-score равен: {f1_score}, baseline равен: {METRIC_THRESHOLD}, решение: {deploy_flag}')
    return deploy_flag

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
    notify = EmailOperator(
        task_id='notify_success',
        to=EMAIL_ADDRESS,
        subject='Переобученная модель ML выведена в прод',
        html_content=f'Новая модель <b>версии {MODEL_VERSION}</b> успешно выведена в прод Yandex Cloud Serverless Containers'
    )

    train >> evaluate >> deploy >> notify