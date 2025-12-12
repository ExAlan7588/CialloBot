# Era TW Discord Game Module
"""
eraTW Discord 遊戲模組

將 eraTW (The World 畫蛇添足版) 移植至 Discord Bot。
"""

from .era_cog import EraCog


async def setup(bot):
    """載入 Era Cog"""
    await bot.add_cog(EraCog(bot))
