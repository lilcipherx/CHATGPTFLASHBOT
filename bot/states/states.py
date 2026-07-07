"""FSM state groups (§6 of the plan)."""
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class MainSG(StatesGroup):
    idle = State()  # plain text -> AI chat


class SearchSG(StatesGroup):
    waiting_query = State()


class PhotoSG(StatesGroup):
    menu = State()
    service_config = State()


class VideoSG(StatesGroup):
    menu = State()
    service_config = State()


class MusicSG(StatesGroup):
    awaiting_prompt = State()


class SettingsSG(StatesGroup):
    role_input = State()


class AvatarSG(StatesGroup):
    awaiting_selfie = State()


class KlingSG(StatesGroup):
    """Kling Effects / Motion template browse → photo upload."""

    browse = State()
    awaiting_photo = State()


class FaceSwapSG(StatesGroup):
    """Face Swap (§15A): 2-step photo upload — target scene then source face."""

    awaiting_target = State()
    awaiting_source = State()


class UpscaleSG(StatesGroup):
    """Upscale X2/X4 (§15A): pick a factor, then send the image to enlarge."""

    awaiting_image = State()
