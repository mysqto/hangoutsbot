import logging, asyncio
import hangups
import plugins

logger = logging.getLogger(__name__)


def _initialise(bot):
    qsms_bot = Forward(bot)

    if qsms_bot.initialised:
        plugins.register_handler(qsms_bot.on_chat_message, type="allmessages")


def get_response_status(response):
    try:
        status = response.response_header.status

        if status != hangups.hangouts_pb2.RESPONSE_STATUS_OK:
            description = response.response_header.error_description
            return 'Request failed with status {}: \'{}\''.format(status, description)
        else:
            return "success"
    except Exception as ex:
        return "unexpected error : {}".format(ex)


def _get_lookup_spec(identifier):
    """Return EntityLookupSpec from phone number, email address, or gaia ID."""
    if identifier.startswith('+'):
        return hangups.hangouts_pb2.EntityLookupSpec(
            phone=identifier, create_offnetwork_gaia=True
        )
    elif '@' in identifier:
        return hangups.hangouts_pb2.EntityLookupSpec(
            email=identifier, create_offnetwork_gaia=True
        )
    else:
        return hangups.hangouts_pb2.EntityLookupSpec(gaia_id=identifier)


class User:
    chat_id = None
    gaia_id = None
    type = None
    name = None

    def __init__(self, chat_id, gaia_id, type, name):
        self.chat_id = chat_id
        self.gaia_id = gaia_id
        self.type = type
        self.name = name


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

    @asyncio.coroutine
    def load_users(self):
        if len(self.users) == 0:
            users = yield from self.lookup_users(self.receivers)
            if users:
                for user in users:
                    if user.chat_id == self.bot.user_self()["chat_id"]:
                        logger.warning("message forward to myself is not supported")
                        continue
                    self.users.append(user)

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
        yield from self.load_users()
        for user in self.users:
            logger.info("user info chat_id = {}, name = {}, type = {}".format(user.chat_id, user.name, user.type))

            """try to get load or create a new conversation_id"""
            conversation_id = yield from self.get_1to1(user)

            if conversation_id:
                response = yield from self.send_message(user, conversation_id, message)
                logger.info("message sent to {}, status : {}".format(user.name, get_response_status(response)))

    @asyncio.coroutine
    def lookup_users(self, identifiers):
        users = []

        for identifier in identifiers:
            """Search for entities by phone number, email, or gaia_id."""
            lookup_spec = _get_lookup_spec(identifier)
            request = hangups.hangouts_pb2.GetEntityByIdRequest(
                request_header=self.bot.client().get_request_header(),
                batch_lookup_spec=[lookup_spec],
            )
            res = yield from self.bot.client().get_entity_by_id(request)

            for entity_result in res.entity_result:
                for entity in entity_result.entity:
                    name = identifier
                    if entity.properties.display_name:
                        name = entity.properties.display_name
                    user = User(entity.id.chat_id, entity.id.gaia_id, entity.entity_type, name)
                    users.append(user)
        return users

    @asyncio.coroutine
    def get_1to1(self, user):
        """
            find/create a 1-to-1 conversation with specified user
        """
        if not user.chat_id:
            logger.warning("")
            return None

        if self.bot.memory.exists(["user_data", user.chat_id, "1on1"]):
            conversation_id = self.bot.memory.get_by_path(["user_data", user.chat_id, "1on1"])
            logger.info("load conversation from memory, conversation_id = {}".format(conversation_id))
        else:
            logger.info("conversation for {} not found in memory, try to create a new one".format(user.chat_id))
            conversation_id = yield from self.create_conversation(user)
            logger.info("new 1to1 conversation created, conversation_id = {}".format(conversation_id))

        if conversation_id is not None:
            # remember the conversation so we don't have to do this again
            logger.info("get_1on1: determined {} for {}".format(conversation_id, user.chat_id))
            self.bot.initialise_memory(user.chat_id, "user_data")
            self.bot.memory.set_by_path(["user_data", user.chat_id, "1on1"], conversation_id)
            self.bot.memory.save()

        return conversation_id

    @asyncio.coroutine
    def create_conversation(self, user):
        request = hangups.hangouts_pb2.CreateConversationRequest(
            request_header=self.bot.client().get_request_header(),
            type=hangups.hangouts_pb2.CONVERSATION_TYPE_ONE_TO_ONE,
            client_generated_id=self.bot.client().get_client_generated_id(),
            invitee_id=[
                hangups.hangouts_pb2.InviteeID(
                    gaia_id=user.gaia_id
                )
            ],
            name=user.name
        )
        res = yield from self.bot.client().create_conversation(request)

        if isinstance(res.conversation, hangups.hangouts_pb2.Conversation):
            return res.conversation.conversation_id.id
        return None

    @asyncio.coroutine
    def send_message(self, user, conversation_id, message):
        otr_status = hangups.hangouts_pb2.OFF_THE_RECORD_STATUS_OFF_THE_RECORD
        request = hangups.hangouts_pb2.SendChatMessageRequest(
            request_header=self.bot.client().get_request_header(),
            event_request_header=hangups.hangouts_pb2.EventRequestHeader(
                conversation_id=hangups.hangouts_pb2.ConversationId(
                    id=conversation_id
                ),
                client_generated_id=self.bot.client().get_client_generated_id(),
                expected_otr=otr_status,
                delivery_medium=hangups.hangouts_pb2.DeliveryMedium(
                    medium_type=hangups.hangouts_pb2.DELIVERY_MEDIUM_BABEL if
                    user.type == hangups.hangouts_pb2.PARTICIPANT_TYPE_GAIA
                    else hangups.hangouts_pb2.DELIVERY_MEDIUM_GOOGLE_VOICE
                )
            ),
            message_content=hangups.hangouts_pb2.MessageContent(
                segment=[
                    hangups.ChatMessageSegment(message).serialize()
                ],
            ),
        )
        response = yield from self.bot.client().send_chat_message(request)

        return response
