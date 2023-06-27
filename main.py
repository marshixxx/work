from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from random import randrange
import requests
import vk_api
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
import threading
import re
import configparser
import db
from messages import *


class VkUser:
    """Класс, использующий токен пользователя, для получения информации при помощи VK API."""
    def get_params(self, add_params: dict = None):
        """Возвращает параметры для соответствующего метода API.

        Подробнее в документации VK API <https://dev.vk.com/api/api-requests>.

        :param add_params: Входные параметры. Опционально.
        :type add_params: dict
        """
        params = {
            'access_token': user_access_token,
            'v': '5.131'
        }
        if add_params:
            params.update(add_params)
            pass
        return params

    def get_user_name(self, user_id):
        """Возвращает имя и фамилию пользователя vk.

        Подробнее в документации VK API <https://dev.vk.com/method/users.get>.

        :param user_id: Идентификатор пользователя vk.
        :type user_id: int
        """
        response = requests.get(
            'https://api.vk.com/method/users.get',
            self.get_params({'user_ids': user_id})
        )
        try:
            for user_info in response.json()['response']:
                first_name = user_info['first_name']
                last_name = user_info['last_name']
                return first_name, last_name
        except:
            print(f"Не удалось получить имя пользователя для {user_id}: {response.json()['error']['error_msg']}")
            VkBot().write_msg(user_id, 'Ошибка с нашей стороны. Попробуйте позже.')
            db.update(user_id, db.UserPosition, position=1, offset=0)
            return False

    def get_city(self, city):
        """Возвращает идентификатор города.

        Подробнее в документации VK API <https://dev.vk.com/method/database.getCities>.

        :param city: Город, полученный в сообщении от пользователя вк.
        :type city: str
        """
        response = requests.get(
            'https://api.vk.com/method/database.getCities',
            self.get_params({'country_id': 1, 'count': 1, 'q': city})
        )
        try:
            response = response.json()['response']['items']
            if not response:
                VkBot().write_msg(user_id, city_unknown)
                city = False
            else:
                for city_id in response:
                    city = city_id['id']
        except:
            print(f"Не удалось получить город пользователя для {user_id}: {response.json()['error']['error_msg']}")
            VkBot().write_msg(user_id, 'Ошибка с нашей стороны. Попробуйте позже.')
            db.update(user_id, db.UserPosition, position=1, offset=0)
            city = False
        return city

    def get_top_photos(self, partner_id):
        """Возвращает список из ссылок на три самые популярные фотографии пользователя.

        Подробнее в документации VK API <https://dev.vk.com/method/photos.get>.

        :param partner_id: Идентификатор пользователя vk.
        :type partner_id: int
        """
        photos = []
        response = requests.get(
            'https://api.vk.com/method/photos.get',
            self.get_params({'owner_id': partner_id,
                             'album_id': 'profile',
                             'extended': 1,
                             'count': 255}
                            )
        )
        try:
            sorted_response = sorted(response.json()['response']['items'],
                                     key=lambda x: x['likes']['count'], reverse=True)
            for photo_id in sorted_response:
                photos.append(f'''photo{partner_id}_{photo_id['id']}''')
            top_photos = ','.join(photos[:3])
            return top_photos
        except:
            print(f"Не удалось получить список фотографий для {user_id}: {response.json()['error']['error_msg']}")
            VkBot().write_msg(user_id, 'Ошибка с нашей стороны. Попробуйте позже.')
            db.update(user_id, db.UserPosition, position=1, offset=0)
            return False

    def find_partner(self):
        """Метод для поиска потенциального партнера в вк и добавление его в базу данных.

        Подробнее в документации VK API <https://dev.vk.com/method/users.search>.
        """
        db_user_id = db.get_db_id(user_id)
        city = db.get_city(user_id)
        sex = db.get_sex(user_id)
        age_from = db.get_age_from(user_id)
        age_to = db.get_age_to(user_id)
        offset = db.get_offset(user_id)
        response = requests.get(
            'https://api.vk.com/method/users.search',
            self.get_params({'count': 1,
                             'offset': offset,
                             'city': city,
                             'country': 1,
                             'sex': sex,
                             'age_from': age_from,
                             'age_to': age_to,
                             'fields': 'is_closed',
                             'status': 6,
                             'has_photo': 1}
                            )
        )
        try:
            response = response.json()['response']['items']
            for partner in response:
                private = partner['is_closed']
                avoid_list = db.avoid_list(db_user_id)
                if private or partner['id'] in avoid_list:
                    offset += 1
                    db.update(user_id, db.UserPosition, offset=offset)
                    self.find_partner()
                else:
                    partner_id = partner['id']
                    first_name = partner['first_name']
                    last_name = partner['last_name']
                    offset += 1
                    db.update(user_id, db.UserPosition, offset=offset)
                    VkBot().offer_partner(partner_id, first_name, last_name)
        except:
            print(f"Не удалось найти партнера для {user_id}: {response.json()['error']['error_msg']}")
            VkBot().write_msg(user_id, 'Ошибка с нашей стороны. Попробуйте позже.')
            db.update(user_id, db.UserPosition, position=1, offset=0)
            return


class VkBot:
    """Класс, использующий токен группы, для общения с пользователем."""
    def __init__(self):
        self.commands = ['привет, прив, ghbdtn, hi, hello, здравствуйте, хай',
                         'старт, поехали, начать, го, go, start, cnfhn',
                         'пока, bye, до свидания, gjrf, выход']

    def write_msg(self, user_id, message, attachment='', **kwargs):
        """Отправить сообщение пользователю.

        Подробнее в документации VK API <https://dev.vk.com/method/messages.send>.

        :param user_id: Идентификатор пользователя vk, которому отправляется сообщение.
        :type user_id: int
        :param message: Текст личного сообщения. Обязательный параметр, если не задан параметр attachment
        :type message: str
        :param attachment: Медиавложения к личному сообщению, перечисленные через запятую.
        Каждое вложение представлено в формате: <type><owner_id>_<media_id>
        :type attachment: str
        :param kwargs: Объекты, описывающие специальные сообщения. Например, клавиатуру.
        """
        try:
            vk.method('messages.send', {'user_id': user_id, 'message': message, 'random_id': randrange(10 ** 7),
                                        'attachment': attachment, **kwargs})
        except Exception as e:
            print(e)

    def chat_keyboard(self, buttons, button_colors):
        """Метод создания новой клавиатуры для бота.

        Подробнее в документации VK API <https://dev.vk.com/api/bots/development/keyboard>.

        :param buttons: Список кнопок.
        :type buttons: list
        :param button_colors: Список цветов кнопок.
        :type button_colors: list
        """
        keyboard = VkKeyboard.get_empty_keyboard()
        keyboard = VkKeyboard(one_time=True)
        for btn, btn_color in zip(buttons, button_colors):
            keyboard.add_button(btn, btn_color)
        return keyboard

    def get_age_range(self, message_text):
        """Возвращает возрастной диапазон в виде списка.

        :param message_text: Возрастной диапазон, полученный в сообщении от пользователя вк.
        :type message_text: str
        """
        age_range = re.findall(r'\d+', message_text)
        age_range = [int(i) for i in age_range]
        try:
            if len(age_range) == 1 and 18 <= age_range[0] <= 100:
                age_range.append(age_range[0])
                return age_range
            elif 18 <= age_range[0] < age_range[1] and age_range[0] < age_range[1] <= 100:
                return age_range
            else:
                self.write_msg(user_id, age_range_unknown)
        except:
            self.write_msg(user_id, age_range_unknown)

    def offer_partner(self, partner_id, first_name, last_name):
        """Отправить пользователю потенциального партнера и его фотографии.

        :param partner_id: Идентификатор партнера в vk.
        :type partner_id: int
        :param first_name: Имя партнера.
        :type first_name: str
        :param last_name: Фамилия партнера.
        :type last_name: str
        """
        db_user_id = db.get_db_id(user_id)
        message = f'Имя: {first_name}\n'\
                  f'Фамилия: {last_name}\n'\
                  f'Ссылка: @id{partner_id}'
        top_photos = VkUser().get_top_photos(partner_id)
        if top_photos:
            buttons = ['Далее', 'В избранное', 'Список избранных']
            button_colors = [VkKeyboardColor.SECONDARY, VkKeyboardColor.POSITIVE, VkKeyboardColor.PRIMARY]
            keyboard = self.chat_keyboard(buttons, button_colors)
            self.write_msg(user_id, message, top_photos, keyboard=keyboard.get_keyboard())
            partner = db.Partner(vk_id=partner_id, first_name=first_name,
                                 last_name=last_name, id_User=db_user_id)
            db.add_user(partner)
        else:
            return

    def show_favorites(self):
        """Отправить пользователю список избранных партнеров."""
        buttons = ['Продолжить поиск', 'Удалить партнера из списка']
        button_colors = [VkKeyboardColor.POSITIVE, VkKeyboardColor.NEGATIVE]
        keyboard = self.chat_keyboard(buttons, button_colors)
        keyboard.add_line()
        keyboard.add_button('Изменить критерии поиска', color=VkKeyboardColor.PRIMARY)
        keyboard.add_button('Выход', color=VkKeyboardColor.SECONDARY)
        partners = db.view_favorites(user_id)
        message = f'Список избранных:\n'
        for partner in partners:
            message += f'@id{partner}\n'
        self.write_msg(user_id, message, keyboard=keyboard.get_keyboard())

    def processing_messages(self, user_id, message_text):
        """Основной метод обработки сообщений пользователя.

        Реализован многоуровневый бот для обработки сообщений сразу от нескольких пользователей с помощью библиотеки
        threading. У каждого пользователя будет свой тред и его текущее положение в базе данных. В зависимости от этого
        положения происходит обработка сообщения, и после обновляется положение пользователя в базе данных на новое, и
        выполняются нужные инструкции.

        :param user_id: Идентификатор пользователя vk.
        :type user_id: int
        :param message_text: Сообщение пользователя.
        :type message_text: str
        """
        position = db.get_position(user_id)

        if message_text in self.commands[2]:
            self.write_msg(user_id, good_bye)
            db.update(user_id, db.UserPosition, position=0)

        elif message_text in self.commands[0] or position == 0:
            buttons = ['Старт']
            button_colors = [VkKeyboardColor.POSITIVE]
            keyboard = self.chat_keyboard(buttons, button_colors)
            self.write_msg(user_id, Hello, keyboard=keyboard.get_keyboard())
            db.add_user(db.User(vk_id=user_id))
            db_user_id = db.get_db_id(user_id)
            db.add_user(db.UserPosition(id_User=db_user_id, vk_id=user_id, position=1, offset=0))

        elif position == 1 or message_text == 'изменить критерии поиска':
            if message_text in self.commands[1] or message_text == 'изменить критерии поиска':
                self.write_msg(user_id, city_input)
                db.update(user_id, db.UserPosition, position=2, offset=0)
            else:
                self.write_msg(user_id, unknown_command)

        elif position == 2:
            city = VkUser().get_city(message_text)
            if city:
                self.write_msg(user_id, age_range_msg)
                db.update(user_id, db.User, city=city)
                db.update(user_id, db.UserPosition, position=3)
            else:
                return

        elif position == 3:
            target_age_range = self.get_age_range(message_text)
            db.update(user_id, db.User, age_from=target_age_range[0], age_to=target_age_range[1])
            buttons = ['Мужской', 'Женский']
            button_colors = [VkKeyboardColor.POSITIVE, VkKeyboardColor.POSITIVE]
            keyboard = self.chat_keyboard(buttons, button_colors)
            self.write_msg(user_id, sex_input, keyboard=keyboard.get_keyboard())
            db.update(user_id, db.UserPosition, position=4)

        elif position == 4:
            if message_text == 'мужской' or message_text == 'женский':
                if message_text == 'мужской':
                    gender = 2
                else:
                    gender = 1
                user_info = VkUser().get_user_name(user_id)
                if user_info:
                    db.update(user_id, db.User, first_name=user_info[0], last_name=user_info[1], target_gender=gender)
                    db.update(user_id, db.UserPosition, position=5)
                    VkUser().find_partner()
                else:
                    return
            else:
                buttons = ['Мужской', 'Женский']
                button_colors = [VkKeyboardColor.POSITIVE, VkKeyboardColor.POSITIVE]
                keyboard = self.chat_keyboard(buttons, button_colors)
                self.write_msg(user_id, unknown_command, keyboard=keyboard.get_keyboard())

        elif position == 5:
            if message_text == 'далее':
                VkUser().find_partner()
            elif message_text == 'в избранное':
                favorite = db.Favorite(vk_id=db.get_partner_id(), first_name=db.get_partner_first_name(),
                                       last_name=db.get_partner_last_name(), id_User=db.get_db_id(user_id))
                db.add_user(favorite)
                self.write_msg(user_id, add_favourite)
                VkUser().find_partner()
            elif message_text == 'список избранных':
                self.show_favorites()
                db.update(user_id, db.UserPosition, position=6)
            else:
                buttons = ['Далее', 'В избранное', 'Список избранных']
                button_colors = [VkKeyboardColor.SECONDARY, VkKeyboardColor.POSITIVE, VkKeyboardColor.PRIMARY]
                keyboard = self.chat_keyboard(buttons, button_colors)
                self.write_msg(user_id, unknown_command, keyboard=keyboard.get_keyboard())

        elif position == 6:
            if message_text == 'продолжить поиск':
                db.update(user_id, db.UserPosition, position=5)
                VkUser().find_partner()
            elif message_text == 'удалить партнера из списка':
                self.write_msg(user_id, id_input)
                db.update(user_id, db.UserPosition, position=7)
            else:
                self.write_msg(user_id, unknown_command)

        elif position == 7:
            if int(message_text) in db.view_favorites(user_id):
                db.delete_user(int(message_text))
                self.write_msg(user_id, delete)
                db.update(user_id, db.UserPosition, position=5)
                VkUser().find_partner()
            else:
                self.write_msg(user_id, id_unknown)
        elif not position:
            VkBot().write_msg(user_id, 'Ошибка с нашей стороны. Попробуйте позже.')
        else:
            self.write_msg(user_id, unknown_command)


if __name__ == '__main__':
    config = configparser.ConfigParser()
    config.read('config.ini')
    group_access_token = config['VK']['GROUP_TOKEN']
    user_access_token = config['VK']['USER_TOKEN']
    group_id = config['VK']['GROUP_ID']
    vk_user = vk_api.VkApi(token=user_access_token)
    vk = vk_api.VkApi(token=group_access_token)
    db.create_tables()
    try:
        longpoll = VkBotLongPoll(vk, group_id)
        while True:
            for event in longpoll.listen():
                if event.type == VkBotEventType.MESSAGE_NEW and event.from_user:
                    user_id = event.object.message['from_id']
                    message = event.object.message['text']
                    thread = threading.Thread(target=VkBot().processing_messages, args=(user_id, message.lower()))
                    thread.start()
    except vk_api.exceptions.ApiError as error_msg:
        print(error_msg)


