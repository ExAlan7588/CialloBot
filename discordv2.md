from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Union
from discord.ext import commands
from discord import ui
import discord
import enum


class FruitType(enum.Enum):
    apple = 'Apple'
    banana = 'Banana'
    orange = 'Orange'
    grape = 'Grape'
    mango = 'Mango'
    watermelon = 'Watermelon'
    coconut = 'Coconut'

    @property
    def emoji(self) -> str:
        emojis = {
            'Apple': '🍎',
            'Banana': '🍌',
            'Orange': '🍊',
            'Grape': '🍇',
            'Mango': '🥭',
            'Watermelon': '🍉',
            'Coconut': '🥥',
        }
        return emojis[self.value]

    def as_option(self) -> discord.SelectOption:
        return discord.SelectOption(label=self.value, emoji=self.emoji, value=self.name)


# This is where we'll store our settings for the purpose of this example.
# In a real application you would want to store this in a database or file.
@dataclass
class Settings:
    fruit_type: FruitType = FruitType.apple
    channel: Optional[discord.PartialMessageable] = None
    members: List[Union[discord.Member, discord.User]] = field(default_factory=list)
    count: int = 1
    silent: bool = False


class Bot(commands.Bot):
    # Suppress error on the User attribute being None since it fills up later
    user: discord.ClientUser

    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.settings: Settings = Settings()

    async def on_ready(self):
        print(f'Logged in as {self.user} (ID: {self.user.id})')
        print('------')


class FruitsSetting(ui.ActionRow['SettingsView']):
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.update_options()

    def update_options(self):
        for option in self.select_fruit.options:
            option.default = option.value == self.settings.fruit_type.name

    @ui.select(placeholder='Select a fruit', options=[fruit.as_option() for fruit in FruitType])
    async def select_fruit(self, interaction: discord.Interaction[Bot], select: discord.ui.Select) -> None:
        self.settings.fruit_type = FruitType[select.values[0]]
        self.update_options()
        await interaction.response.edit_message(view=self.view)


class ChannelSetting(ui.ActionRow['SettingsView']):
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        if settings.channel is not None:
            self.select_channel.default_values = [
                discord.SelectDefaultValue(id=settings.channel.id, type=discord.SelectDefaultValueType.channel)
            ]

    @ui.select(
        placeholder='Select a channel',
        channel_types=[discord.ChannelType.text, discord.ChannelType.public_thread],
        max_values=1,
        min_values=0,
        cls=ui.ChannelSelect,
    )
    async def select_channel(self, interaction: discord.Interaction[Bot], select: ui.ChannelSelect) -> None:
        if select.values:
            channel = select.values[0]
            self.settings.channel = interaction.client.get_partial_messageable(
                channel.id, guild_id=channel.guild_id, type=channel.type
            )
            select.default_values = [discord.SelectDefaultValue(id=channel.id, type=discord.SelectDefaultValueType.channel)]
        else:
            self.settings.channel = None
            select.default_values = []
        await interaction.response.edit_message(view=self.view)


class MembersSetting(ui.ActionRow['SettingsView']):
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.update_options()

    def update_options(self):
        self.select_members.default_values = [
            discord.SelectDefaultValue(id=member.id, type=discord.SelectDefaultValueType.user)
            for member in self.settings.members
        ]

    @ui.select(placeholder='Select members', max_values=5, min_values=0, cls=ui.UserSelect)
    async def select_members(self, interaction: discord.Interaction[Bot], select: ui.UserSelect) -> None:
        self.settings.members = select.values
        self.update_options()
        await interaction.response.edit_message(view=self.view)


class CountModal(ui.Modal, title='Set emoji count'):
    count = ui.TextInput(label='Count', style=discord.TextStyle.short, default='1', required=True)

    def __init__(self, view: 'SettingsView', button: SetCountButton):
        super().__init__()
        self.view = view
        self.settings = view.settings
        self.button = button

    async def on_submit(self, interaction: discord.Interaction[Bot]) -> None:
        try:
            self.settings.count = int(self.count.value)
            self.button.label = str(self.settings.count)
            await interaction.response.edit_message(view=self.view)
        except ValueError:
            await interaction.response.send_message('Invalid count. Please enter a number.', ephemeral=True)


class SetCountButton(ui.Button['SettingsView']):
    def __init__(self, settings: Settings):
        super().__init__(label=str(settings.count), style=discord.ButtonStyle.secondary)
        self.settings = settings

    async def callback(self, interaction: discord.Interaction[Bot]) -> None:
        # Tell the type checker that a view is attached already
        assert self.view is not None
        await interaction.response.send_modal(CountModal(self.view, self))


class NotificationToggleButton(ui.Button['SettingsView']):
    def __init__(self, settings: Settings):
        super().__init__(label='\N{BELL}', style=discord.ButtonStyle.green)
        self.settings = settings
        self.update_button()

    def update_button(self):
        if self.settings.silent:
            self.label = '\N{BELL WITH CANCELLATION STROKE} Disabled'
            self.style = discord.ButtonStyle.red
        else:
            self.label = '\N{BELL} Enabled'
            self.style = discord.ButtonStyle.green

    async def callback(self, interaction: discord.Interaction[Bot]) -> None:
        self.settings.silent = not self.settings.silent
        self.update_button()
        await interaction.response.edit_message(view=self.view)


class SettingsView(ui.LayoutView):
    row = ui.ActionRow()

    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings

        # For this example, we'll use multiple sections to organize the settings.
        container = ui.Container()
        header = ui.TextDisplay('# Settings\n-# This is an example to showcase how to do settings.')
        container.add_item(header)
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large))

        self.count_button = SetCountButton(self.settings)
        container.add_item(
            ui.Section(
                ui.TextDisplay('## Emoji Count\n-# This is the number of times the emoji will be repeated in the message.'),
                accessory=self.count_button,
            )
        )
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small))
        container.add_item(
            ui.Section(
                ui.TextDisplay(
                    '## Notification Settings\n-# This controls whether the bot will use silent messages or not.'
                ),
                accessory=NotificationToggleButton(self.settings),
            )
        )
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large))
        container.add_item(ui.TextDisplay('## Fruit Selection\n-# This is the fruit that is shown in the message.'))
        container.add_item(FruitsSetting(self.settings))
        container.add_item(ui.TextDisplay('## Channel Selection\n-# This is the channel where the message will be sent.'))
        container.add_item(ChannelSetting(self.settings))
        container.add_item(
            ui.TextDisplay('## Member Selection\n-# These are the members that will be mentioned in the message.')
        )
        container.add_item(MembersSetting(self.settings))
        self.add_item(container)

        # Swap the row so it's at the end
        self.remove_item(self.row)
        self.add_item(self.row)

    @row.button(label='Finish', style=discord.ButtonStyle.green)
    async def finish_button(self, interaction: discord.Interaction[Bot], button: ui.Button) -> None:
        # Edit the message to make it the interaction response...
        await interaction.response.edit_message(view=self)
        # ...and then send a confirmation message.
        await interaction.followup.send(f'Settings saved.', ephemeral=True)
        # Then delete the settings panel
        self.stop()
        await interaction.delete_original_response()


bot = Bot()


@bot.command()
async def settings(ctx: commands.Context[Bot]):
    """Shows the settings view."""
    view = SettingsView(ctx.bot.settings)
    await ctx.send(view=view)


@bot.command()
async def send(ctx: commands.Context[Bot]):
    """Sends the message with the current settings."""
    settings = ctx.bot.settings

    if settings.channel is None:
        await ctx.send('No channel is configured. Please use the settings command to set one.')
        return

    # This example is super silly, so don't do this for real. It's annoying.
    content = ' '.join(settings.fruit_type.emoji for _ in range(settings.count))
    mentions = ' '.join(member.mention for member in settings.members)

    await settings.channel.send(content=f'{mentions} {content}', silent=settings.silent)


bot.run('token')
from __future__ import annotations

from discord.ext import commands
from discord import ui
import discord
import aiohttp


class Bot(commands.Bot):
    # Suppress error on the User attribute being None since it fills up later
    user: discord.ClientUser

    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)

    async def setup_hook(self) -> None:
        # Create a session for making HTTP requests.
        self.session = aiohttp.ClientSession()

    async def close(self) -> None:
        # Close the session when the bot is shutting down.
        await self.session.close()
        await super().close()

    async def on_ready(self):
        print(f'Logged in as {self.user} (ID: {self.user.id})')
        print('------')

    async def get_random_dog_image(self) -> str:
        async with self.session.get('https://random.dog/woof.json') as resp:
            js = await resp.json()
            return js['url']


# This is a row of buttons that will be used in our larger LayoutView later.
# An ActionRow is similar to a View but it can only contain up to 5 buttons or 1 select menu.
# Similar to a View it can be inherited to make it easier to manage.
class EmbedChangeButtons(ui.ActionRow):
    def __init__(self, view: 'EmbedLikeView') -> None:
        self.__view = view
        super().__init__()

    @ui.button(label='New Image', style=discord.ButtonStyle.gray)
    async def new_image(self, interaction: discord.Interaction[Bot], button: discord.ui.Button) -> None:
        url = await interaction.client.get_random_dog_image()
        self.__view.thumbnail.media.url = url
        await interaction.response.edit_message(view=self.__view)

    @ui.button(label='Change Text', style=discord.ButtonStyle.primary)
    async def change_text(self, interaction: discord.Interaction[Bot], button: discord.ui.Button) -> None:
        await interaction.response.send_modal(ChangeTextModal(self.__view))


# This is a simple modal to allow the content of the text portion of the "embed" to be changed by the user.
class ChangeTextModal(ui.Modal, title='Change Text'):
    new_text = ui.TextInput(label='The new text', style=discord.TextStyle.long)

    def __init__(self, view: 'EmbedLikeView') -> None:
        self.__view = view
        self.new_text.default = view.random_text.content
        super().__init__()

    async def on_submit(self, interaction: discord.Interaction, /) -> None:
        self.__view.random_text.content = str(self.new_text.value)
        await interaction.response.edit_message(view=self.__view)
        self.stop()


# This defines a simple LayoutView that uses a Container to wrap its contents
# A Container is similar to an Embed, in that it has an accent colour and darkened background.
# It differs from an Embed in that it can contain other items, such as buttons, galleries, or sections, etc.
class EmbedLikeView(ui.LayoutView):
    def __init__(self, *, url: str) -> None:
        super().__init__()

        # When we want to use text somewhere, we can wrap it in a TextDisplay object so it becomes an Item.
        self.random_text = ui.TextDisplay('This is a random dog image! Press the button to change it and this text!')
        # A thumbnail is an Item that can be used to display an image as a thumbnail.
        # It needs to be wrapped inside a Section object to be used.
        # A Section is a container that can hold 3 TextDisplay and an accessory.
        # The accessory can either be a Thumbnail or a Button.
        # Since we're emulating an Embed, we will use a Thumbnail.
        self.thumbnail = ui.Thumbnail(media=url)
        self.section = ui.Section(self.random_text, accessory=self.thumbnail)
        self.buttons = EmbedChangeButtons(self)

        # Wrap all of this inside a Container
        # To visualize how this looks, you can think of it similar to this ASCII diagram:
        # +----------------------Container--------------------+
        # | +--------------------Section--------------------+ |
        # | | +----------------------------+  +-Thumbnail-+ | |
        # | | |  TextDisplay               |  | Accessory | | |
        # | | |                            |  |           | | |
        # | | |                            |  |           | | |
        # | | |                            |  |           | | |
        # | | +----------------------------+  +-----------+ | |
        # | +-----------------------------------------------+ |
        # | +------------------ActionRow--------------------+ |
        # | |+-------------+ +-------------+                | |
        # | || Button A    | | Button B    |                | |
        # | |+-------------+ +-------------+                | |
        # | +-----------------------------------------------+ |
        # +---------------------------------------------------+

        # If you want the "embed" to have multiple images you can add a MediaGallery item
        # to the container as well, which lets you have up to 10 images in a grid-like gallery.

        container = ui.Container(self.section, self.buttons, accent_color=discord.Color.blurple())
        self.add_item(container)


bot = Bot()


@bot.command()
async def embed(ctx: commands.Context[Bot]):
    """Shows the basic Embed-like LayoutView."""
    url = await ctx.bot.get_random_dog_image()
    # Note that when sending LayoutViews, you cannot send any content, embeds, stickers, or polls.
    await ctx.send(view=EmbedLikeView(url=url))


bot.run('token')
Components V2
Aug 17, 2025  pipythonmc
Discord.py 2.6 brings support for Discord’s new components system (known as “Components V2”), which allows you to mix text, media, and interactive components when composing bot messages.

Some important things to know:

Old components are not going away. They will continue to be supported by both Discord and discord.py.
You can continue to use ui.View under the old system, even if you have other parts of your bot using the new ui.LayoutView.
You cannot send content, embeds, stickers, or polls in a message using the new components. New components provide the functionality of content and embeds.
LayoutView #
The ui.LayoutView class replaces ui.View as the base class for all of your views. This is required in order to use the new components.

At the time of writing, the limit on total components contained in a LayoutView is 40. This includes nested components.

class Layout(discord.ui.LayoutView):
    # you can add any top-level component here

    text = discord.ui.TextDisplay("Hello, Components V2!")

    action_row = discord.ui.ActionRow()

    @action_row.button(label = "A Button")
    async def a_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Clicked!", ephemeral = True)
Top-level components #
These components can be placed directly in a LayoutView.

Text display #
ui.TextDisplay allows placing regular text content in your layout. Markdown is supported. Note that mentions placed in the text will ping users/roles/everyone even if the text display is within a container. The character limit (4000 at time of writing) is shared across all text displays in the same LayoutView.

Action row #
ui.ActionRow is a container for buttons and select menus. It can be subclassed and used with @ui.button/@ui.select or directly in a LayoutView as shown by the example above.

The documentation page has examples of both usages.

Section #
ui.Section allows placing text and an accessory side-by-side, where the accessory can be either a thumbnail or button.

section = discord.ui.Section(
    "Text can be directly passed as strings, which will be wrapped in a TextDisplay automatically.",
    discord.ui.TextDisplay("Or you can pass a TextDisplay."),
    accessory = MyCustomButtonSubclass()
)
Separator #
ui.Separator adds visual spacing between components. You can set the amount of space taken (large or small) and whether a line should be visible to the user.

Media Gallery #
discord.ui.MediaGallery allows displaying images and videos in a gallery. Entries are specified as discord.MediaGalleryItems. The current limit is 1-10 media items per gallery.

As a shortcut, you can pass a discord.File object into MediaGalleryItem. The file still needs to be specified when sending your message.

file1 = discord.File("secret_message.png")
file2 = discord.File("example.jpg")

gallery = discord.ui.MediaGallery(
    discord.MediaGalleryItem("https://some.image/url.png", description = "Alt text"),
    discord.MediaGalleryItem("attachment://secret_message.png", spoiler = True),
    discord.MediaGalleryItem(file2),
)

# later:
await channel.send(view = view, files = [file1, file2])
File #
discord.ui.File allows displaying files in your message. These will not display a preview. Note that your discord.File needs to be included when sending the message.

Similar to MediaGalleryItem in the previous section, discord.ui.File also supports passing discord.File as the media argument.

Container #
discord.ui.Container can contain other top-level components. Visually, it displays a border similar to an embed with an optional accent color.

class MyContainer(discord.ui.Container):
    text = discord.ui.TextDisplay("This appears inside a box!")

class MyLayout(discord.ui.LayoutView):
    container = MyContainer(accent_color = 0x7289da)
Non-top-level components #
These cannot be placed directly under a LayoutView or Container.

Buttons and select menus #
These have not changed from old components. However, you must manually place them in an action row to include them in LayoutViews.

You might be interested in reading more about the different types of select menus.

Thumbnail #
discord.ui.Thumbnail represents an image displayed on the right of a section.

section = discord.ui.Section(
    "Text content",
    accessory = discord.ui.Thumbnail("attachment://thumb.png")
)
Using with webhooks #
Non-bot webhooks can now send non-interactive components by passing a view to Webhook.send.

Component ids #
All components now have a numerical id property. This is different from the custom_id property of interactive components. Manually setting the id and using LayoutView.find_item can help with managing deeply nested items.

import discord
from discord import ui

COUNT_TRACKER_ID = 100027

class CounterButton(ui.Button):
    async def callback(self, i: discord.Interaction):
        self.view.count += 1

        text_display = self.view.find_item(COUNT_TRACKER_ID)
        text_display.content = f"The current count is {self.view.count}."

        await i.response.edit_message(view = self.view)

class MyCounterLayout(discord.ui.LayoutView):
    count = 0

    container = discord.ui.Container(
        discord.ui.Section(
            discord.ui.TextDisplay(
                f"The current count is {count}.",
                id = COUNT_TRACKER_ID,
            ),
            accessory = CounterButton(label = "+1"),
        )
    )
Migrating persistent views #
If the same buttons/select menus with the same custom_ids are present in a LayoutView, migrating from a persistent View to a persistent LayoutView should work as you expect. In fact, Discord allows you to edit messages that did not use new components to use new components, as long as you clear content/embeds by setting it to None in your edit. However, you cannot edit a message back to using old components.

In Components V2, containers are similar to embeds but are still different:
Embeds
Fields
Inlines
Title, Description, Author and Footer
Timestamp
6000 Max characters
One Image
One Thumbnail
Text

Cv2
Use all components with extreme flexibility
Multiple Images
Multiple Sections (i.e thumbnail/button + 3 TextDisplay)
Must use TextDisplay, cannot use the regular content 
You can actually ping users, roles, @​here, @​everyone, etc.
Colours
Can have no colours at all
Use markdown anywhere
4000 Max Characters Accumutatively

Components V2 is an extension to the existing components, allowing you to mix text content, media, and interactive components together in a message. You can use these starting in discord.py 2.6.

Can I see an example?
See ?tag cv2 example for examples.
See discord.py/components-v2 for a guide.
See ?tag cv2tags for other cv2-related tags.

Does this break existing bots?
No. You must opt in to use the new components. The old components are not deprecated and will not be removed. Your bot can use both component systems at the same time (since the opt-in is per-message).

What does this add?
New components that allow greater flexibility when composing messages:
Text displays - message content, but as a component. Regular markdown works here.
Sections - allows putting text and an accessory side by side. Currently you can use buttons and thumbnails as accessories.
Media galleries - display 1-10 images in a gallery
Files - displaying inline, rather than below the message. Will not embed image previews - use a media gallery with a single image instead.
Separators - a horizontal line (or just a gap, it's configurable)
Containers - renders like an embed box, can contain most of the above. Text displays that have mentions will ping users/roles/everyone, even when inside a container.

What limitations are there?
Cannot send regular message content, embeds, stickers, or polls in the same message as components v2.
Text displays and containers essentially replace content/embeds.
Container does not (and probably will not) support fields, author, or footer.
Links in text displays do not automatically embed a website preview.
Can switch old messages to use components v2, but cannot convert a components v2 message back to a regular message with content/embeds.