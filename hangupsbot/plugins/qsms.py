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
    receivers = []
    keywords = []
    template_id = None
    sms_sign = None
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

                receivers = config['receivers']
                keywords = config['keywords']

                if receivers:
                    self.receivers = list(set(receivers))
                if keywords:
                    self.keywords = list(set(keywords))

            except Exception as e:
                logger.warning("error loading qsms configuration {} : {}".format(config, e))

        logger.info(
            "config: app_id = {}, app_key= {}, template_id = {}, sms_sign = {} default = {}".format(self.app_id,
                                                                                                    self.app_key,
                                                                                                    self.template_id,
                                                                                                    self.sms_sign,
                                                                                                    self.default))
        logger.info("receivers = {}, keywords= {}".format(self.receivers, self.keywords))

        if self.app_id and self.app_key and len(self.receivers) > 0 and len(
                self.keywords) > 0 and self.template_id and self.sms_sign and self.default:
            self.initialised = True

    def on_chat_message(self, bot, event, command):

        message = event.text

        for keyword in self.keywords:
            logger.info("keyword = {}".format(keyword))
            if keyword in message:
                params = self.extract_verification_code(message)
                if isinstance(params, list):
                    logger.info('extracted verification code: {}'.format(params))
                    self.send_sms(params)
                break

    def send_sms(self, params):
        sender = SmsMultiSender(self.app_id, self.app_key)

        try:
            result = sender.send_with_param(86, self.receivers,
                                            self.template_id, params, sign=self.sms_sign, extend="", ext="")
        except HTTPError as e:
            logger.warning("error sending sms {} : {}".format(params, e))
        except Exception as e:
            logger.warning("error sending sms {} : {}".format(params, e))
        logger.info('SMS send with result {}'.format(result))

    def extract_verification_code(self, message):
        result = []

        # search for sign
        regex = r'(\[.*\]|【.*】)'
        pm = re.search(regex, message)

        if pm is not None:
            result.append(str(pm.group(0))[1:-1])
        else:
            result.append(self.default)

        regex = r'(\d{8}|\d{7}|\d{6}|\d{3} \d{3}|\d{5}|\d{4})'
        pm = re.search(regex, message)

        if pm is None:
            return None

        result.append(str(pm.group(0)))

        return result
