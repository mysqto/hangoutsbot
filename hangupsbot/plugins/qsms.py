import os, logging, re

import hangups

from qcloudsms_py import SmsMultiSender
from qcloudsms_py.httpclient import HTTPError

import plugins

logger = logging.getLogger(__name__)


def _initialise(bot):
    qsms_bot = QSmsBot(bot)

    if qsms_bot.initialised:
        plugins.register_handler(qsms_bot.on_chat_message, type="allmessages")


class QSmsBot:
    bot = None
    app_id = None
    app_key = None
    default = None
    code_regex = None
    sign_regex = None
    country_code = None
    receivers = []
    keywords = []
    template_id = None
    sms_sign = None
    sender = None
    initialised = False

    def __init__(self, bot):
        self.bot = bot
        self.initialised = False

        config = bot.get_config_option('qsms')

        if isinstance(config, dict):
            try:
                self.app_id = os.getenv('APP_ID', None)
                if self.app_id is None:
                    self.app_id = config['app_id']

                self.app_key = os.getenv('APP_KEY', None)
                if self.app_key is None:
                    self.app_key = config['app_key']

                self.template_id = os.getenv('TEMPLATE_ID', None)

                if self.template_id is None:
                    self.template_id = config['template_id']

                self.sms_sign = os.getenv('SMS_SIGN', None)

                if self.sms_sign is None:
                    self.sms_sign = config['sms_sign']

                self.default = config['default_product']
                self.code_regex = config['code_regex']
                self.sign_regex = config['sign_regex']
                self.country_code = config['country_code']

                if self.country_code is None:
                    self.country_code = 86

                receivers = config['receivers']
                keywords = config['keywords']

                if receivers:
                    self.receivers = list(set(receivers))
                if keywords:
                    self.keywords = list(set(keywords))

            except Exception as e:
                logger.warning("error loading qsms configuration {} : {}".format(config, e))

        logger.info('config: app_id = {}, app_key= {}'.format(self.app_id, self.app_key))
        logger.info('code_regex = {}, sign_regex= {}'.format(self.code_regex, self.sign_regex))
        logger.info('template_id = {}, sms_sign = {}'.format(self.template_id, self.sms_sign))
        logger.info('default = {}, country_code = {}'.format(self.default, self.country_code))
        logger.info("receivers = {}, keywords= {}".format(self.receivers, self.keywords))

        if self.app_id and self.app_key and len(self.receivers) > 0 and len(
                self.keywords) > 0 and self.template_id and self.sms_sign and self.country_code\
                and self.default and self.sign_regex and self.code_regex:
            self.initialised = True

        if self.initialised:
            self.sender = SmsMultiSender(self.app_id, self.app_key)

    def on_chat_message(self, bot, event, command):

        if event.user.id_.chat_id == self.bot.user_self()["chat_id"]:
            logger.warning("message from myself is not supported")
            return

        message = event.text

        for keyword in self.keywords:
            if keyword in message:
                params = self.extract_verification_code(message)
                if isinstance(params, list):
                    logger.info('extracted application and verification code: {}'.format(params))
                    self.send_sms(params)
                break

    def send_sms(self, params):

        try:
            result = self.sender.send_with_param(86, self.receivers, self.template_id,
                                                 params, sign=self.sms_sign, extend="", ext="")
        except HTTPError as e:
            logger.warning("error sending sms {} : {}".format(params, e))
        except Exception as e:
            logger.warning("error sending sms {} : {}".format(params, e))

        logger.info('SMS send with result {}'.format(result))

    def extract_verification_code(self, message):
        result = []

        # search for sign
        pm = re.search(self.sign_regex, message)

        if pm is not None:
            result.append(str(pm.group(0))[1:-1])
        else:
            result.append(self.default)

        pm = re.search(self.code_regex, message)

        if pm is None:
            return None

        result.append(str(pm.group(0)).replace(" ", ""))

        return result
