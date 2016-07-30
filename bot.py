#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import telegram
import sys
from pyslack import SlackClient
import json
import argparse
import time
import os
import traceback
import urllib3
import itertools
from datetime import datetime
from pony.orm import db_session, select
from db import botDB, Chat


BOT_DESCRIPTION = "Бот для распределения людей по палаткам"
LAST_UPDATE_ID = None
MESSAGE_ALARM = "Аларм! Аларм!"
CHAT_ID_ALARM = 79031498
BOT_ID = 136777319
#SEND_BROAD_CMD = '/send_broad'
#SEND_MSG_CMD = '/send'
USER_LIST_CMD = '/user_list'
TELEGRAM_MSG_CHANNEL = '#telegram-messages'



def main():
    global LAST_UPDATE_ID

    parser = argparse.ArgumentParser(description=BOT_DESCRIPTION)
    parser.add_argument("--logfile", type=str, default='log', help="Path to log file")
    parser.add_argument("--dbfile", type=str, default='tentme.sqlite', help="Path to sqlite DB file")
    args = parser.parse_args()

    botDB.bind('sqlite', args.dbfile, create_db=True)
    botDB.generate_mapping(create_tables=True)

    # TODO: use it
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    telegram_token = open('.telegram_token').readline().strip()
    bot = telegram.Bot(telegram_token)

    try:
        LAST_UPDATE_ID = bot.getUpdates()[-1].update_id
    except IndexError:
        LAST_UPDATE_ID = None

    while True:
        try:
            run(bot, args.logfile)
        except telegram.TelegramError as error:
            print "TelegramError", error
            time.sleep(1)
        except SystemExit:
            exit()
        #except urllib2.URLError as error:
        #    print "URLError", error
        #    time.sleep(1)
        except:
            traceback.print_exc()
            try:
                bot.sendMessage(chat_id=CHAT_ID_ALARM, text=MESSAGE_ALARM)
            except:
                pass
            time.sleep(100) # 100 seconds


def log_update(update, logfile):
    with open(logfile, 'a') as log:
        log.write(update.to_json().decode('unicode-escape').encode('utf-8') + '\n')


def update_chat_db(message):
    with db_session:
        chat = Chat.get(chat_id=message.chat.id)
        if chat == None:
            chat = Chat(chat_id=message.chat.id, user_id=message.from_user.id, open_date=datetime.now(), \
                        last_message_date=datetime.now(), username=message.from_user.username, \
                        first_name=message.from_user.first_name, last_name=message.from_user.last_name, \
                        silent_mode=False, deleted=False, group_id="nobody", state="REGISTER_STATE", \
                        realname="", contacts="", places="1", masterskaya="", gender="male")
        else:
            chat.last_message_date = datetime.now()
            chat.username = message.from_user.username
            chat.first_name = message.from_user.first_name
            chat.last_name = message.from_user.last_name

        return chat


def send_broad(bot, text, group):
    with db_session:
        for chat in select(chat for chat in Chat if not (chat.silent_mode or chat.deleted) and \
                           (chat.group_id == group or group == "all")):
            try:
                #is_admin = 
                #reply_markup = MAIN_KEYBOARD_ADMIN if is_admin else MAIN_KEYBOARD
                bot.sendMessage(chat_id=chat.chat_id, text=text)#, reply_markup=reply_markup)
            except telegram.TelegramError as error:
                print "TelegramError", error


def forward_broad(bot, from_chat_id, message_id, group):
    with db_session:
        for chat in select(chat for chat in Chat if not (chat.silent_mode or chat.deleted) and \
                           (chat.group_id == group or group == "all")):
            try:
                #is_admin = 
                #reply_markup = MAIN_KEYBOARD_ADMIN if is_admin else MAIN_KEYBOARD
                #bot.sendMessage(chat_id=chat.chat_id, text=text)#, reply_markup=reply_markup)
                bot.forwardMessage(chat_id=chat.chat_id, from_chat_id=from_chat_id, message_id=message_id)
            except telegram.TelegramError as error:
                print "TelegramError", error


def send_large_message(bot, chat_id, text):
    MAX_LINES = 100

    def grouper(iterable, n, fillvalue=None):
        "Collect data into fixed-length chunks or blocks"
        # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx
        args = [iter(iterable)] * n
        return itertools.izip_longest(fillvalue=fillvalue, *args)

    lines = text.splitlines()
    for block in grouper(lines, MAX_LINES, ''):
        bot.sendMessage(chat_id=chat_id, text='\n'.join(block))


def print_userlist(bot, message):
    with db_session:
        chats_str = ''
        for chat in select(chat for chat in Chat):
            chats_str += u'{}. {} (@{}, {})'.format(chat.primary_id, chat.realname, \
                                                     chat.username, chat.group_id)
            if chat.silent_mode:
                chats_str += ' (silent mode)'
            if chat.deleted:
                chats_str += ' (deleted)'
            chats_str += '\n'

        try:
            pass
            #send_large_message(bot, message.chat_id, chats_str)
        except telegram.TelegramError as error:
            print "TelegramError", error


        need_str = u'Нужна палатка:\n'
        for chat in select(chat for chat in Chat if "need" in chat.group_id):
            need_str += u'{}. {} (@{}), пол: {}, мастерская: {}. Контакты: {}'.format(chat.primary_id, chat.realname, chat.username, \
                                                                 chat.gender, chat.masterskaya, chat.contacts)
        try:
            send_large_message(bot, message.chat_id, need_str)
        except telegram.TelegramError as error:
            print "TelegramError", error


        give_str = u'Дают палатку:\n'
        for chat in select(chat for chat in Chat if "give" in chat.group_id):
            give_str += u'{}. {} (@{}), пол: {}, мест в палатке: {}. Контакты: {}'.format(chat.primary_id, chat.realname, chat.username, \
                                                                 chat.gender, chat.places, chat.contacts)
        try:
            send_large_message(bot, message.chat_id, give_str)
        except telegram.TelegramError as error:
            print "TelegramError", error



def send_message(bot, message):
    with db_session:
        cmd = text = ''
        primary_id = 0
        params = message.text.split(' ', 2)
        if len(params) > 0:
            cmd = params[0]
        if len(params) > 1:
            try:
                primary_id = int(params[1])
            except ValueError:
                bot.sendMessage(chat_id=message.chat_id, text='cannot find user')
                return False
        if len(params) > 2:
            text = params[2]
        if primary_id == 0:
            bot.sendMessage(chat_id=message.chat_id, text='cannot send message to empty user')
        elif len(text) == 0:
            bot.sendMessage(chat_id=message.chat_id, text='cannot send empty message')
        else:
            chat = Chat.get(primary_id=primary_id)
            if chat == None:
                bot.sendMessage(chat_id=message.chat_id, text='cannot find user')
            elif chat.deleted:
                bot.sendMessage(chat_id=message.chat_id, text='this user marked as deleted')
            else:
                bot.sendMessage(chat_id=chat.chat_id, text=text)


def run(bot, logfile):
    global LAST_UPDATE_ID
    for update in bot.getUpdates(offset=LAST_UPDATE_ID, timeout=10):
        message = update.message

        chat = update_chat_db(message)
        primary_id, group_id, state, silent_mode, deleted, realname, contacts, username, places, gender, masterskaya = \
            chat.primary_id, chat.group_id, chat.state, chat.silent_mode, chat.deleted, \
            chat.realname, chat.contacts, chat.username, chat.places, chat.gender, chat.masterskaya

        log_update(update, logfile)

        #automata_step(message, chat)

        #if group_id == "admin":
        #    reply_markup = '{"keyboard" : [["/user_list"]], "resize_keyboard" : true, "one_time_keyboard" : true}'
        #else:
        #    reply_markup = telegram.ReplyKeyboardHide()

        print(u"State: {}. Message: {}".format(state, message.text))

        if state.startswith("REGISTER_STATE"):
            if len(state.split()) == 1:
                text = u"Привет! Вы попали в бот, распределяющий людей по палаткам."
                bot.sendMessage(chat_id=message.chat_id, text=text)
                if not username:
                    reply_markup = '{"keyboard" : [["/continue"]], "resize_keyboard" : true, "one_time_keyboard" : true}'
                    text = u"Пожалуйста, установите username в настройках (Settings) Телеграма, чтобы остальные могли с Вами связаться"
                    bot.sendMessage(chat_id=message.chat_id, text=text, reply_markup=reply_markup)
                else:
                    reply_markup = '{"keyboard" : [["/continue"]], "resize_keyboard" : true, "one_time_keyboard" : true}'
                    text = u"По username @{} с Вами могут связываться остальные. Введите свой телефон для связи или нажмите /continue:".format(username)
                    bot.sendMessage(chat_id=message.chat_id, text=text, reply_markup=reply_markup)
                    state = "REGISTER_STATE contacts"
            elif len(state.split()) == 2:
                if message.text != "/continue":
                    contacts = message.text
                text = u"Вы готовы предоставить место в палатке (/give) или Вам оно нужно (/need)?"
                reply_markup = '{"keyboard" : [["/give", "/need"]], "resize_keyboard" : true, "one_time_keyboard" : true}'
                bot.sendMessage(chat_id=message.chat_id, text=text, reply_markup=reply_markup)
                state = "REGISTER_STATE contacts group"
            elif len(state.split()) == 3:
                if message.text == "/give":
                    state = "REGISTER_STATE contacts group give"
                    group_id = "give"
                    text = u"Сколько мест в палатке Вы можете предоставить?"
                    reply_markup = '{"keyboard" : [["1", "2", "3"]], "resize_keyboard" : true, "one_time_keyboard" : true}'
                    bot.sendMessage(chat_id=message.chat_id, text=text, reply_markup=reply_markup)
                elif message.text == "/need":
                    state = "REGISTER_STATE contacts group need"
                    group_id = "need"
                    text = u"Из какой Вы мастерской?"
                    bot.sendMessage(chat_id=message.chat_id, text=text, reply_markup=telegram.ReplyKeyboardHide())
                else:
                    pass
            elif state.split()[3] == "give":
                if len(state.split()) == 4:
                    places = message.text
                    reply_markup = '{"keyboard" : [["/female", "/male"]], "resize_keyboard" : true}'
                    text = u'Введите Ваш пол ("/female", "/male"):'
                    bot.sendMessage(chat_id=message.chat_id, text=text, reply_markup=reply_markup)
                    state = "REGISTER_STATE contacts group give gender"
                elif len(state.split()) == 5:
                    if message.text == "/male":
                        gender = "male"
                    elif message.text == "/female":
                        gender = "female"
                    else:
                        gender = message.text
                    reply_markup = '{"keyboard" : [["/register", "/unregister"]], "resize_keyboard" : true}'
                    text = u"Ваша заявка зарегистрирована! Нажмите /register для перерегистрации или /unregister, если Ваша больше не актуальна."
                    bot.sendMessage(chat_id=message.chat_id, text=text, reply_markup=reply_markup)
                    state = "MAIN_STATE"
            elif state.split()[3] == "need":
                if len(state.split()) == 4:
                    masterskaya = message.text
                    reply_markup = '{"keyboard" : [["/female", "/male"]], "resize_keyboard" : true}'
                    text = u'Введите Ваш пол ("/female", "/male"):'
                    bot.sendMessage(chat_id=message.chat_id, text=text, reply_markup=reply_markup)
                    state = "REGISTER_STATE contacts group need gender"
                elif len(state.split()) == 5:
                    if message.text == "/male":
                        gender = "male"
                    elif message.text == "/female":
                        gender = "female"
                    else:
                        gender = message.text
                    reply_markup = '{"keyboard" : [["/register", "/unregister"]], "resize_keyboard" : true}'
                    text = u"Ваша заявка зарегистрирована! Нажмите /register для перерегистрации или /unregister, если Ваша больше не актуальна."
                    bot.sendMessage(chat_id=message.chat_id, text=text, reply_markup=reply_markup)
                    state = "MAIN_STATE"

        elif state.startswith("MAIN_STATE"):
            if message.text == "I am god":
                group_id += "_admin"
                reply_markup = '{"keyboard" : [["/user_list", "/register", "/unregister"]], "resize_keyboard" : true}'
                bot.sendMessage(chat_id=message.chat_id, text="Вы админ! Вам доступен /user_list", reply_markup=reply_markup)
            elif message.left_chat_member != None:
                if message.left_chat_member.id == BOT_ID:
                    deleted = True
            elif message.new_chat_member != None:
                if message.new_chat_member.id == BOT_ID:
                    deleted = False
            elif message.text == "/unregister":
                if "admin" in group_id:
                    group_id = "admin"
                else:
                    group_id = "done"
                reply_markup = '{"keyboard" : [["/register"]], "resize_keyboard" : true}'
                text = u"Ваша заявка больше не актуальна! Нажмите /register для новой регистрации."
                bot.sendMessage(chat_id=message.chat_id, text=text, reply_markup=reply_markup)
            elif message.text == "/register":
                    reply_markup = '{"keyboard" : [["/continue"]], "resize_keyboard" : true, "one_time_keyboard" : true}'
                    text = u"По username @{} с Вами могут связываться остальные. Введите свой телефон для связи или нажмите /continue:".format(username)
                    bot.sendMessage(chat_id=message.chat_id, text=text, reply_markup=reply_markup)
                    state = "REGISTER_STATE contacts"
            elif message.text == USER_LIST_CMD:
                print_userlist(bot, message)
            elif "admin" in group_id and message.text == "/killme":
                exit()
            else:
                pass


        with db_session:
            chat = Chat.get(chat_id=message.chat.id)


            chat.primary_id, chat.group_id, chat.state, chat.silent_mode, chat.deleted, \
                chat.realname, chat.contacts, chat.username, chat.places, chat.gender, chat.masterskaya = \
                primary_id, group_id, state, silent_mode, deleted, realname, contacts, username, places, gender, masterskaya

        LAST_UPDATE_ID = update.update_id + 1



if __name__ == '__main__':
    main()
