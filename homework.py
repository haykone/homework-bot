import logging
import os
import sys
import time
from http import HTTPStatus

import requests
from dotenv import load_dotenv
from telebot import TeleBot

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    """Проверка доступности переменных окружения."""
    tokens = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID,
    }
    missing_tokens = []
    for key, value in tokens.items():
        if not value:
            missing_tokens.append(key)

    if missing_tokens:
        logging.critical(f'Отсутствует токен: {', '.join(missing_tokens)}')
        return False
    return True


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logging.debug(f'Бот отправил сообщение: {message}')
        return True
    except (requests.RequestException, Exception) as error:
        logging.error(f'Сбой при отправке сообщения в Telegram: {error}')
        return False


def get_api_answer(timestamp):
    """Делает запрос к эндпоинту API-сервиса."""
    payload = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS,
                                params=payload)
    except requests.RequestException as error:
        raise ConnectionError(f'Ошибка при запросе к основному API: {error}')

    if response.status_code != HTTPStatus.OK:
        raise RuntimeError(f'Эндпоинт {ENDPOINT} недоступен.'
                           f'Код ответа: {response.status_code}')

    return response.json()


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if not isinstance(response, dict):
        raise TypeError(
            f'Ожидался словарь, но пришел {type(response).__name__}'
        )

    if 'homeworks' not in response:
        raise KeyError('В ответе API отсутствует ключ "homeworks"')

    if not isinstance(response.get('homeworks'), list):
        raise TypeError('Под ключом "homeworks" ожидался список')


def parse_status(homework):
    """Извлекает статус работы и возвращает строку с вердиктом."""
    if 'homework_name' not in homework:
        raise KeyError('В ответе API отсутствует ключ "homework_name"')

    homework_name = homework.get('homework_name')

    if 'status' not in homework:
        raise KeyError(
            'В ответе API для работы "{homework_name}" отсутствует статус')

    status = homework.get('status')

    if status not in HOMEWORK_VERDICTS:
        raise ValueError('Неизвестный статус работы: {status}')

    verdict = HOMEWORK_VERDICTS[status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        sys.exit(1)

    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_error = ''

    while True:
        try:
            response = get_api_answer(timestamp)
            check_response(response)
            last_error = ''
            
            homeworks = response.get('homeworks')
            if homeworks:
                message = parse_status(homeworks[0])
                if send_message(bot, message):
                    timestamp = response.get('current_date', timestamp)
            else:
                logging.debug('Новых статусов в ответе нет')

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logging.error(message)
            error_text = str(error)
            if error_text != last_error and send_message(bot, message):
                last_error = error_text

        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        format='%(asctime)s - %(levelname)s - %(message)s',
        level=logging.INFO,
        handlers=[
            logging.FileHandler('bot.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    main()
