import logging, asyncio
import plugins

logger = logging.getLogger(__name__)


def _initialise(bot):
    qsms_bot = Forward(bot)

    if qsms_bot.initialised:
        plugins.register_handler(qsms_bot.on_chat_message, type="allmessages")


class Forward:
    bot = None
    receivers = []
    keywords = []
    initialised = False
    users = []

    def __init__(self, bot):
        self.bot = bot

        config = bot.get_config_option('forward')

        if isinstance(config, dict):
            try:
                receivers = config['receivers']
                keywords = config['keywords']

                if receivers:
                    self.receivers = list(set(receivers))
                if keywords:
                    self.keywords = list(set(keywords))

            except Exception as e:
                logger.warning("error loading forward configuration {} : {}".format(config, e))

        logger.info('config: receivers = {}, keywords = {}'.format(self.receivers, self.keywords))

        if len(self.receivers) > 0 and len(self.keywords) > 0:
            self.initialised = True

    def on_chat_message(self, bot, event, command):
        if event.user.id_.chat_id == self.bot.user_self()["chat_id"]:
            logger.warning("message from myself is not supported")
            return

        message = event.text

        for keyword in self.keywords:
            if keyword in message:
                logger.info("forward keyword {} triggered, message : {}".format(keyword, message))
                yield from self.send(message)
                break

    @asyncio.coroutine
    def send(self, message):
        for receiver in self.receivers:
            yield from self.bot.coro_send_message_to_user(receiver, message)