import shutil

from tabpfn_client.service_wrapper import UserAuthenticationClient, InferenceClient
from tabpfn_client.client import ServiceClient
from tabpfn_client.constants import CACHE_DIR
from tabpfn_client.prompt_agent import PromptAgent


class TabPFNConfig:
    is_initialized = None
    user_email = None
    use_server = None
    user_auth_handler = None
    inference_handler = None


g_tabpfn_config = TabPFNConfig()


def init(use_server=True):
    # initialize config
    use_server = use_server
    global g_tabpfn_config

    if use_server:
        PromptAgent.prompt_welcome()

        service_client = ServiceClient()
        user_auth_handler = UserAuthenticationClient(service_client)

        # check connection to server
        if not user_auth_handler.is_accessible_connection():
            raise RuntimeError(
                "TabPFN is inaccessible at the moment, please try again later."
            )

        is_valid_token_set = user_auth_handler.try_reuse_existing_token()

        if is_valid_token_set:
            PromptAgent.prompt_reusing_existing_token()
        else:
            if not PromptAgent.prompt_terms_and_cond():
                raise RuntimeError(
                    "You must agree to the terms and conditions to use TabPFN"
                )

            # prompt for login / register
            g_tabpfn_config.user_email = PromptAgent.prompt_and_set_token(user_auth_handler)

        # Print new greeting messages. If there are no new messages, nothing will be printed.
        PromptAgent.prompt_retrieved_greeting_messages(
            user_auth_handler.retrieve_greeting_messages()
        )

        g_tabpfn_config.use_server = True
        g_tabpfn_config.user_auth_handler = user_auth_handler
        g_tabpfn_config.inference_handler = InferenceClient(service_client)

    else:
        g_tabpfn_config.use_server = False

    g_tabpfn_config.is_initialized = True


def reset():
    # reset config
    global g_tabpfn_config
    g_tabpfn_config = TabPFNConfig()

    # reset user auth handler
    if g_tabpfn_config.use_server:
        g_tabpfn_config.user_auth_handler.reset_cache()

    # remove cache dir
    shutil.rmtree(CACHE_DIR, ignore_errors=True)
