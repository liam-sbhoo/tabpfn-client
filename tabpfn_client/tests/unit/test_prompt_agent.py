import unittest
from unittest.mock import patch
from tabpfn_client.prompt_agent import PromptAgent


class TestPromptAgent(unittest.TestCase):
    def test_password_req_to_policy(self):
        password_req = ["Length(8)", "Uppercase(1)", "Numbers(1)", "Special(1)"]
        password_policy = PromptAgent.password_req_to_policy(password_req)
        requirements = [repr(req) for req in password_policy.test("")]
        self.assertEqual(password_req, requirements)

    @patch(
        "tabpfn_client.prompt_agent.PromptAgent.prompt_terms_and_cond",
        return_value=True,
    )
    @patch(
        "tabpfn_client.prompt_agent.getpass.getpass",
        side_effect=["Password123!", "Password123!"],
    )
    @patch(
        "builtins.input",
        side_effect=["1", "user@gmail.com", "test", "test", "test", "y", "test"],
    )
    def test_prompt_and_set_token_registration(
        self,
        mock_input,
        mock_getpass,
        mock_prompt_terms_and_cond,
    ):
        # for some reason, it needs to be patched with a with-statement instead of a decorator
        with patch(
            "tabpfn_client.prompt_agent.UserAuthenticationClient"
        ) as mock_auth_client:
    
            mock_auth_client.try_browser_login.return_value = (False, None)
            mock_auth_client.get_password_policy.return_value = [
                    "Length(8)",
                    "Uppercase(1)",
                    "Numbers(1)",
                    "Special(1)",
                ]
            mock_auth_client.set_token_by_registration.return_value = (
                True,
                "Registration successful",
                "dummy_token",
            )
            mock_auth_client.validate_email.return_value = (True, "")
            mock_auth_client.verify_email.return_value = (
                True,
                "Verification successful",
            )

    
            with patch("builtins.print"):
                PromptAgent.prompt_and_set_token()

            mock_auth_client.validate_email.assert_called_once_with("user@gmail.com")
    
            mock_auth_client.try_browser_login.assert_called_once()
            mock_auth_client.validate_email.assert_called_once_with("user@gmail.com")
            mock_auth_client.set_token_by_registration.assert_called_once_with(
                "user@gmail.com",
                "Password123!",
                "Password123!",
                "tabpfn-2023",
                {
                    "company": "test",
                    "role": "test",
                    "use_case": "test",
                    "contact_via_email": True,
                },
            )

    @patch(
        "tabpfn_client.prompt_agent.PromptAgent.prompt_terms_and_cond",
        return_value=True,
    )
    @patch("getpass.getpass", return_value="password123")
    @patch("builtins.input", side_effect=["2", "user@gmail.com"])
    def test_prompt_and_set_token_login(self, mock_input, mock_getpass):
        mock_auth_client = MagicMock()
        mock_auth_client.set_token_by_login.return_value = (True, "Login successful")
        PromptAgent.prompt_and_set_token(user_auth_handler=mock_auth_client)
        mock_auth_client.set_token_by_login.assert_called_once()

    @patch("builtins.input", return_value="y")
    def test_prompt_terms_and_cond_returns_true(self, mock_input):
        result = PromptAgent.prompt_terms_and_cond()
        self.assertTrue(result)

    @patch("builtins.input", return_value="n")
    def test_prompt_terms_and_cond_returns_false(self, mock_input):
        result = PromptAgent.prompt_terms_and_cond()
        self.assertFalse(result)

    @patch("builtins.input", return_value="1")
    def test_choice_with_retries_valid_first_try(self, mock_input):
        result = PromptAgent._choice_with_retries(
            "Please enter your choice: ", ["1", "2"]
        )
        self.assertEqual(result, "1")

    @patch("builtins.input", side_effect=["3", "3", "1"])
    def test_choice_with_retries_valid_third_try(self, mock_input):
        result = PromptAgent._choice_with_retries(
            "Please enter your choice: ", ["1", "2"]
        )
        self.assertEqual(result, "1")
