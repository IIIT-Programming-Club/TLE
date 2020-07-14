import random
import datetime
import discord
import asyncio
import itertools
import challonge
import urllib
import cairosvg

from discord.ext import commands
from collections import defaultdict, namedtuple
from matplotlib import pyplot as plt

from tle.util.db.user_db_conn import Duel, DuelType, Winner
from tle.util import codeforces_api as cf
from tle.util import codeforces_common as cf_common
from tle.util import paginator
from tle.util import discord_common
from tle.util import table
from tle.util import graph_common as gc

from os import environ

_DUEL_INVALIDATE_TIME = 2 * 60
_DUEL_EXPIRY_TIME = 5 * 60
_DUEL_RATING_DELTA = -400
_DUEL_NO_DRAW_TIME = 10 * 60
_ELO_CONSTANT = 60

_USERNAME = 'Groverkss'
_API = 'API'

curr_tour = None

DuelRank = namedtuple(
    'Rank', 'low high title title_abbr color_graph color_embed')

DUEL_RANKS = (
    DuelRank(-10 ** 9, 1300, 'Newbie', 'N', '#CCCCCC', 0x808080),
    DuelRank(1200, 1400, 'Pupil', 'P', '#77FF77', 0x008000),
    DuelRank(1400, 1600, 'Specialist', 'S', '#77DDBB', 0x03a89e),
    DuelRank(1600, 1900, 'Expert', 'E', '#AAAAFF', 0x0000ff),
    DuelRank(1900, 2100, 'Candidate Master', 'CM', '#FF88FF', 0xaa00aa),
    DuelRank(2100, 2300, 'Master', 'M', '#FFCC88', 0xff8c00),
    DuelRank(2300, 2400, 'International Master', 'IM', '#FFBB55', 0xf57500),
    DuelRank(2400, 2600, 'Grandmaster', 'GM', '#FF7777', 0xff3030),
    DuelRank(2600, 3000, 'International Grandmaster',
             'IGM', '#FF3333', 0xff0000),
    DuelRank(3000, 10 ** 9, 'Legendary Grandmaster',
             'LGM', '#AA0000', 0xcc0000)
)


def rating2rank(rating):
    for rank in DUEL_RANKS:
        if rank.low <= rating < rank.high:
            return rank


class DuelCogError(commands.CommandError):
    pass


def elo_prob(player, opponent):
    return (1 + 10**((opponent - player) / 400))**-1


def elo_delta(player, opponent, win):
    return _ELO_CONSTANT * (win - elo_prob(player, opponent))


def get_cf_user(userid, guild_id):
    handle = cf_common.user_db.get_handle(userid, guild_id)
    return cf_common.user_db.fetch_cf_user(handle)


async def get_tour(index):
    """Get the current tournament if it is not already taken"""

    global curr_tour
    status = cf_common.user_db.get_tour_status()

    if status is 1 and curr_tour is None:
        challonge_user = await challonge.get_user(_USERNAME, _API)
        curr_tour = await challonge_user.get_tournament(url=f'progclub{index}')


async def complete_duel(duelid, guild_id, win_status, winner, loser, finish_time, score, dtype):
    winner_r = cf_common.user_db.get_duel_rating(winner.id)
    loser_r = cf_common.user_db.get_duel_rating(loser.id)
    delta = round(elo_delta(winner_r, loser_r, score))
    rc = cf_common.user_db.complete_match(
        duelid, win_status, finish_time, winner.id, loser.id, delta, dtype)
    if rc == 0:
        raise DuelCogError('Hey! No cheating!')

    global curr_tour
    index = cf_common.user_db.get_tour_index()
    await get_tour(index)

    req_player = None
    players = await curr_tour.get_participants(force_update=True)
    for player in players:
        if player.misc == str(winner.id):
            req_player = player
            break

    match = await req_player.get_next_match()
    if match.player1_id == req_player.id:
        await match.report_winner(req_player, "1-0")
    else:
        await match.report_winner(req_player, "0-1")


async def create_tour(ctx, index):
    """Creates an instance of tournament at challonge"""
    global curr_tour

    challonge_user = await challonge.get_user(_USERNAME, _API)
    challonge_tour = await challonge_user.create_tournament(name=f'IIIT Programing Club Dueling Tournament {index}', url=f'progclub{index}')
    curr_tour = challonge_tour

    users = [(ctx.guild.get_member(user_id), user_id)
             for user_id, aux in cf_common.user_db.get_contestants()]
    users = [(member.display_name, user_id)
             for member, user_id in users
             if member is not None and
             cf_common.user_db.get_handle(user_id, ctx.guild.id) is not None]

    for d_name, user_id in users:
        await challonge_tour.add_participant(d_name, misc=user_id)

    await challonge_tour.start()


async def destroy_tour(index):
    """Destroys the current tournament"""
    global curr_tour
    curr_tour = None


async def get_ranklist(index):
    url = f'https://challonge.com/progclub{index}.svg'
    req = urllib.request.Request(
        url, headers={'User-Agent': 'Mozilla/5.0'})
    data = urllib.request.urlopen(req).read()
    text = data.decode('utf-8')
    cairosvg.svg2png(text, write_to='ranklist.png')


class Tournament(commands.Cog):
    def __init__(self, bot):
        global curr_tour, _API

        _API = environ.get('CHALLONGE_API')

        self.bot = bot
        self.converter = commands.MemberConverter()
        self.draw_offers = {}

    @commands.group(brief='Tournament commands',
                    invoke_without_command=True)
    async def tour(self, ctx):
        """Group for commands pertaining to Tournaments"""
        await ctx.send_help(ctx.command)

    @tour.command(brief='Register yourself for the tournament')
    async def register(self, ctx):
        """Register yourself for the tournament"""
        rc = cf_common.user_db.register_contestant(ctx.author.id)
        if rc == 0:
            raise DuelCogError(
                'You are already a registered contestant')
        await ctx.send(f'Successfully registered {ctx.author.mention} as a contestant.')

    @tour.command(brief='Begin the tournament!!')
    @commands.has_any_role('Admin', 'Moderator')
    async def begin(self, ctx):
        """Starts the tournament"""
        status = cf_common.user_db.get_tour_status()
        if status is 1:
            raise DuelCogError(f'A tournament is already going on!')

        cf_common.user_db.update_tour_status(1)
        index = cf_common.user_db.get_tour_index()
        await create_tour(ctx, index)

    @tour.command(brief='Stop the tournament')
    @commands.has_any_role('Admin', 'Moderator')
    async def destroy(self, ctx):
        """Destroys the current tournament"""
        status = cf_common.user_db.get_tour_status()
        if status is 0:
            raise DuelCogError(f'Tournament is not going on :/')
        index = cf_common.user_db.get_tour_index()
        await destroy_tour(index)
        cf_common.user_db.update_tour_status(0)
        cf_common.user_db.update_tour_index()

    @tour.command(brief='Sends the current standings of the current tournament')
    async def standings(self, ctx):
        """Gets the ranklist of the tournament"""
        status = cf_common.user_db.get_tour_status()
        if status is 0:
            raise DuelCogError(f'Tournament is not going on :/')
        index = cf_common.user_db.get_tour_index()
        await get_tour(index)
        await get_ranklist(index)
        with open('ranklist.png', "rb") as file:
            img = discord.File(file, filename='ranklist.png')
        await ctx.send(file=img)

    @tour.command(brief='Challenge to a duel')
    async def challenge(self, ctx, opponent: discord.Member, rating: int = None):
        """Challenge another server member to a duel. Only works if you have a pending challenge against the other server member in the ongoing tournament. Specify a rating agreed by both as a paramter"""
        status = cf_common.user_db.get_tour_status()
        if status is 0:
            raise DuelCogError(f'Tournament is not going on :/')

        challenger_id = ctx.author.id
        challengee_id = opponent.id

        await cf_common.resolve_handles(ctx, self.converter, ('!' + str(ctx.author), '!' + str(opponent)))
        userids = [challenger_id, challengee_id]
        handles = [cf_common.user_db.get_handle(
            userid, ctx.guild.id) for userid in userids]
        submissions = [await cf.user.status(handle=handle) for handle in handles]

        if challenger_id == challengee_id:
            raise DuelCogError(
                f'{ctx.author.mention}, You know how a tournament works right?')
        if cf_common.user_db.check_tour_match(challenger_id) or cf_common.user_db.check_tour_match(challenger_id):
            raise DuelCogError(
                f'{ctx.author.mention}, you are currently in a duel!')
        if cf_common.user_db.check_tour_match(challengee_id) or cf_common.user_db.check_tour_match(challengee_id):
            raise DuelCogError(
                f'{opponent.display_name} is currently in a duel!')

        global curr_tour
        index = cf_common.user_db.get_tour_index()
        await get_tour(index)

        req_player = None
        players = await curr_tour.get_participants(force_update=True)
        for player in players:
            if player.misc == str(challenger_id):
                req_player = player

        if req_player is None:
            raise DuelCogError(
                f'{ctx.author.mention}, You are not in the tournament :(')

        req_match = await req_player.get_next_match()

        if req_match is None:
            raise DuelCogError(
                f'{ctx.author.mention}, You have lost :(')
        if req_match.state != 'open':
            raise DuelCogError(
                f'{ctx.author.mention}, Your opponent has not finished their match yet')

        player1 = await curr_tour.get_participant(
            req_match.player1_id, force_update=True)
        player2 = await curr_tour.get_participant(
            req_match.player2_id, force_update=True)

        if player1.misc != str(challengee_id) and player2.misc != str(challengee_id):
            raise DuelCogError(
                f'{ctx.author.mention}, You dont have a pending challenge against this person')

        users = [cf_common.user_db.fetch_cf_user(handle) for handle in handles]
        lowest_rating = min(user.rating for user in users)
        suggested_rating = max(
            round(lowest_rating, -2) + _DUEL_RATING_DELTA, 500)
        rating = round(rating, -2) if rating else suggested_rating
        dtype = DuelType.OFFICIAL

        solved = {
            sub.problem.name for subs in submissions for sub in subs if sub.verdict != 'COMPILATION_ERROR'}
        seen = {name for userid in userids for name,
                in cf_common.user_db.get_duel_problem_names(userid)}
        seen2 = {name for userid in userids for name,
                 in cf_common.user_db.get_match_problem_names(userid)}

        def get_problems(rating):
            return [prob for prob in cf_common.cache2.problem_cache.problems
                    if prob.rating == rating
                    and prob.name not in solved
                    and prob.name not in seen
                    and prob.name not in seen2
                    and not any(cf_common.is_contest_writer(prob.contestId, handle) for handle in handles)
                    and not cf_common.is_nonstandard_problem(prob)]

        for problems in map(get_problems, range(rating, 400, -100)):
            if problems:
                break

        rstr = f'{rating} rated ' if rating else ''
        if not problems:
            raise DuelCogError(
                f'No unsolved {rstr}problems left for {ctx.author.mention} vs {opponent.mention}.')

        problems.sort(key=lambda problem: cf_common.cache2.contest_cache.get_contest(
            problem.contestId).startTimeSeconds)

        choice = max(random.randrange(len(problems)) for _ in range(2))
        problem = problems[choice]

        issue_time = datetime.datetime.now().timestamp()
        duelid = cf_common.user_db.create_match(
            challenger_id, challengee_id, issue_time, problem, dtype)

        unofficial = False

        ostr = 'an **unofficial**' if unofficial else 'a'
        await ctx.send(f'{ctx.author.mention} is challenging {opponent.mention} to {ostr} {rstr}duel!')
        await asyncio.sleep(_DUEL_EXPIRY_TIME)
        if cf_common.user_db.cancel_match(duelid, Duel.EXPIRED):
            await ctx.send(f'{ctx.author.mention}, your request to duel {opponent.display_name} has expired!')

    @ tour.command(brief='Decline a duel')
    async def decline(self, ctx):
        active = cf_common.user_db.check_match_decline(ctx.author.id)
        if not active:
            raise DuelCogError(
                f'{ctx.author.mention}, you are not being challenged!')

        duelid, challenger = active
        challenger = ctx.guild.get_member(challenger)
        cf_common.user_db.cancel_match(duelid, Duel.DECLINED)
        await ctx.send(f'{ctx.author.display_name} declined a challenge by {challenger.mention}.')

    @ tour.command(brief='Withdraw a challenge')
    async def withdraw(self, ctx):
        active = cf_common.user_db.check_match_withdraw(ctx.author.id)
        if not active:
            raise DuelCogError(
                f'{ctx.author.mention}, you are not challenging anyone.')

        duelid, challengee = active
        challengee = ctx.guild.get_member(challengee)
        cf_common.user_db.cancel_match(duelid, Duel.WITHDRAWN)
        await ctx.send(f'{ctx.author.mention} withdrew a challenge to {challengee.display_name}.')

    @ tour.command(brief='Accept a duel')
    async def accept(self, ctx):
        active = cf_common.user_db.check_match_accept(ctx.author.id)
        if not active:
            raise DuelCogError(
                f'{ctx.author.mention}, you are not being challenged.')

        duelid, challenger_id, name = active
        challenger = ctx.guild.get_member(challenger_id)
        await ctx.send(f'Duel between {challenger.mention} and {ctx.author.mention} starting in 15 seconds!')
        await asyncio.sleep(15)

        start_time = datetime.datetime.now().timestamp()
        rc = cf_common.user_db.start_match(duelid, start_time)
        if rc != 1:
            raise DuelCogError(
                f'Unable to start the duel between {challenger.mention} and {ctx.author.mention}.')

        problem = cf_common.cache2.problem_cache.problem_by_name[name]
        title = f'{problem.index}. {problem.name}'
        desc = cf_common.cache2.contest_cache.get_contest(
            problem.contestId).name
        embed = discord.Embed(
            title=title, url=problem.url, description=desc)
        embed.add_field(name='Rating', value=problem.rating)
        await ctx.send(f'Starting duel: {challenger.mention} vs {ctx.author.mention}', embed=embed)

    @ tour.command(brief='Complete a duel')
    async def complete(self, ctx):
        active = cf_common.user_db.check_match_complete(ctx.author.id)
        if not active:
            raise DuelCogError(f'{ctx.author.mention}, you are not in a duel.')

        duelid, challenger_id, challengee_id, start_time, problem_name, contest_id, index, dtype = active

        UNSOLVED = 0
        TESTING = -1

        async def get_solve_time(userid):
            handle = cf_common.user_db.get_handle(userid, ctx.guild.id)
            subs = [sub for sub in await cf.user.status(handle=handle)
                    if (sub.verdict == 'OK' or sub.verdict == 'TESTING')
                    and sub.problem.contestId == contest_id
                    and sub.problem.index == index]

            if not subs:
                return UNSOLVED
            if 'TESTING' in [sub.verdict for sub in subs]:
                return TESTING
            return min(subs, key=lambda sub: sub.creationTimeSeconds).creationTimeSeconds

        challenger_time = await get_solve_time(challenger_id)
        challengee_time = await get_solve_time(challengee_id)

        if challenger_time == TESTING or challengee_time == TESTING:
            await ctx.send(f'Wait a bit, {ctx.author.mention}. A submission is still being judged.')
            return

        challenger = ctx.guild.get_member(challenger_id)
        challengee = ctx.guild.get_member(challengee_id)

        if challenger_time and challengee_time:
            if challenger_time != challengee_time:
                diff = cf_common.pretty_time_format(
                    abs(challengee_time - challenger_time), always_seconds=True)
                winner = challenger if challenger_time < challengee_time else challengee
                loser = challenger if challenger_time > challengee_time else challengee
                win_status = Winner.CHALLENGER if winner == challenger else Winner.CHALLENGEE
                await complete_duel(duelid, ctx.guild.id, win_status, winner, loser, min(
                    challenger_time, challengee_time), 1, dtype)
                await ctx.send(f'Both {challenger.mention} and {challengee.mention} solved it but {winner.mention} was {diff} faster!')
            else:
                await complete_duel(duelid, ctx.guild.id, Winner.DRAW,
                                    challenger, challengee, challenger_time, 0.5, dtype)
                await ctx.send(f"{challenger.mention} and {challengee.mention} solved the problem in the exact same amount of time! It's a draw!")

        elif challenger_time:
            await complete_duel(duelid, ctx.guild.id, Winner.CHALLENGER,
                                challenger, challengee, challenger_time, 1, dtype)
            await ctx.send(f'{challenger.mention} beat {challengee.mention} in a duel!')
        elif challengee_time:
            await complete_duel(duelid, ctx.guild.id, Winner.CHALLENGEE,
                                challengee, challenger, challengee_time, 1, dtype)
            await ctx.send(f'{challengee.mention} beat {challenger.mention} in a duel!')
        else:
            await ctx.send('Nobody solved the problem yet.')

    @ tour.command(brief='Offer/Accept a draw')
    async def draw(self, ctx):
        active = cf_common.user_db.check_match_draw(ctx.author.id)
        if not active:
            raise DuelCogError(f'{ctx.author.mention}, you are not in a duel.')

        duelid, challenger_id, challengee_id, start_time, dtype = active
        now = datetime.datetime.now().timestamp()

        if not duelid in self.draw_offers:
            self.draw_offers[duelid] = ctx.author.id
            offeree_id = challenger_id if ctx.author.id != challenger_id else challengee_id
            offeree = ctx.guild.get_member(offeree_id)
            await ctx.send(f'{ctx.author.mention} is offering a draw to {offeree.mention}!')
            return

        if self.draw_offers[duelid] == ctx.author.id:
            await ctx.send(f'{ctx.author.mention}, you\'ve already offered a draw.')
            return

        offerer = ctx.guild.get_member(self.draw_offers[duelid])
        embed = complete_duel(duelid, ctx.guild.id, Winner.DRAW,
                              offerer, ctx.author, now, 0.5, dtype)
        await ctx.send(f'{ctx.author.mention} accepted draw offer by {offerer.mention}.', embed=embed)

    def _paginate_duels(self, data, message, guild_id, show_id):
        def make_line(entry):
            duelid, start_time, finish_time, name, challenger, challengee, winner = entry
            duel_time = cf_common.pretty_time_format(
                finish_time - start_time, shorten=True, always_seconds=True)
            problem = cf_common.cache2.problem_cache.problem_by_name[name]
            when = cf_common.days_ago(start_time)
            idstr = f'{duelid}: '
            if winner != Winner.DRAW:
                loser = get_cf_user(challenger if winner ==
                                    Winner.CHALLENGEE else challengee, guild_id)
                winner = get_cf_user(challenger if winner ==
                                     Winner.CHALLENGER else challengee, guild_id)
                return f'{idstr if show_id else str()}[{name}]({problem.url}) [{problem.rating}] won by [{winner.handle}]({winner.url}) vs [{loser.handle}]({loser.url}) {when} in {duel_time}'
            else:
                challenger = get_cf_user(challenger, guild_id)
                challengee = get_cf_user(challengee, guild_id)
                return f'{idstr if show_id else str()}[{name}]({problem.url}) [{problem.rating}] drawn by [{challenger.handle}]({challenger.url}) and [{challengee.handle}]({challengee.url}) {when} after {duel_time}'

        def make_page(chunk):
            log_str = '\n'.join(make_line(entry) for entry in chunk)
            embed = discord_common.cf_color_embed(description=log_str)
            return message, embed

        if not data:
            raise DuelCogError(f'There are no duels to show.')

        return [make_page(chunk) for chunk in paginator.chunkify(data, 7)]

    @ tour.command(brief='Print list of ongoing matches in the tournament')
    async def ongoing(self, ctx, member: discord.Member = None):
        def make_line(entry):
            start_time, name, challenger, challengee = entry
            problem = cf_common.cache2.problem_cache.problem_by_name[name]
            now = datetime.datetime.now().timestamp()
            when = cf_common.pretty_time_format(
                now - start_time, shorten=True, always_seconds=True)
            challenger = get_cf_user(challenger, ctx.guild.id)
            challengee = get_cf_user(challengee, ctx.guild.id)
            return f'[{challenger.handle}]({challenger.url}) vs [{challengee.handle}]({challengee.url}): [{name}]({problem.url}) [{problem.rating}] {when}'

        def make_page(chunk):
            message = f'List of ongoing matches:'
            log_str = '\n'.join(make_line(entry) for entry in chunk)
            embed = discord_common.cf_color_embed(description=log_str)
            return message, embed

        member = member or ctx.author
        data = cf_common.user_db.get_ongoing_matches()
        if not data:
            raise DuelCogError('There are no ongoing matches.')

        pages = [make_page(chunk) for chunk in paginator.chunkify(data, 7)]
        paginator.paginate(self.bot, ctx.channel, pages,
                           wait_time=5 * 60, set_pagenum_footers=True)

    @ tour.command(brief='Prints list of pending matches in the tournament')
    async def pending(self, ctx, member: discord.Member = None):

        def make_line(entry):
            challenger, challengee = entry
            challenger = get_cf_user(challenger, ctx.guild.id)
            challengee = get_cf_user(challengee, ctx.guild.id)
            return f'[{challenger.handle}]({challenger.url}) vs [{challengee.handle}]({challengee.url})'

        def make_page(chunk):
            message = f'List of pending matches:'
            log_str = '\n'.join(make_line(entry) for entry in chunk)
            embed = discord_common.cf_color_embed(description=log_str)
            return message, embed

        status = cf_common.user_db.get_tour_status()
        if status is 0:
            raise DuelCogError(f'Tournament is not going on :/')
        global curr_tour
        index = cf_common.user_db.get_tour_index()
        await get_tour(index)
        matches = await curr_tour.get_matches(force_update=True)
        data = []
        for match in matches:
            if match.state == 'open':
                player1 = await curr_tour.get_participant(match.player1_id)
                player2 = await curr_tour.get_participant(match.player2_id)
                data.append((player1.misc, player2.misc))

        if not data:
            raise DuelCogError('There are no pending matches.')

        pages = [make_page(chunk) for chunk in paginator.chunkify(data, 7)]
        paginator.paginate(self.bot, ctx.channel, pages,
                           wait_time=5 * 60, set_pagenum_footers=True)

    @ tour.command(brief="Show registered contestants")
    async def registered(self, ctx):
        """Show the list of register contestants."""
        users = [(ctx.guild.get_member(user_id))
                 for user_id, aux in cf_common.user_db.get_contestants()]
        users = [(member, cf_common.user_db.get_handle(member.id, ctx.guild.id))
                 for member in users
                 if member is not None]
        users = [(member, handle)
                 for member, handle in users
                 if handle is not None]

        _PER_PAGE = 10

        def make_page(chunk, page_num):
            style = table.Style('{:>}  {:<}  {:<}')
            t = table.Table(style)
            t += table.Header('#', 'Name', 'Handle')
            t += table.Line()
            for index, (member, handle) in enumerate(chunk):
                t += table.Data(_PER_PAGE * page_num + index,
                                f'{member.display_name}', handle)

            table_str = f'```\n{t}\n```'
            embed = discord_common.cf_color_embed(description=table_str)
            return 'List of contestants', embed

        if not users:
            raise DuelCogError('There are no registered contestants.')

        pages = [make_page(chunk, k) for k, chunk in enumerate(
            paginator.chunkify(users, _PER_PAGE))]
        paginator.paginate(self.bot, ctx.channel, pages,
                           wait_time=5 * 60, set_pagenum_footers=True)

    async def invalidate_duel(self, ctx, duelid, challenger_id, challengee_id):
        rc = cf_common.user_db.invalidate_match(duelid)
        if rc == 0:
            raise DuelCogError(f'Unable to invalidate duel {duelid}.')

        challenger = ctx.guild.get_member(challenger_id)
        challengee = ctx.guild.get_member(challengee_id)
        await ctx.send(f'Duel between {challenger.mention} and {challengee.mention} has been invalidated.')

    @ tour.command(brief='Invalidate the duel')
    async def invalidate(self, ctx):
        """Declare your duel invalid. Use this if you've solved the problem prior to the duel.
        You can only use this functionality during the first 60 seconds of the duel."""
        active = cf_common.user_db.check_match_complete(ctx.author.id)
        if not active:
            raise DuelCogError(f'{ctx.author.mention}, you are not in a duel.')

        duelid, challenger_id, challengee_id, start_time, _, _, _, _ = active
        if datetime.datetime.now().timestamp() - start_time > _DUEL_INVALIDATE_TIME:
            raise DuelCogError(
                f'{ctx.author.mention}, you can no longer invalidate your duel.')
        await self.invalidate_duel(ctx, duelid, challenger_id, challengee_id)

    @ tour.command(brief='Invalidate a duel', usage='[duelist]')
    @ commands.has_any_role('Admin', 'Moderator')
    async def _invalidate(self, ctx, member: discord.Member):
        """Declare an ongoing duel invalid."""
        active = cf_common.user_db.check_match_complete(member.id)
        if not active:
            raise DuelCogError(f'{member.display_name} is not in a duel.')

        duelid, challenger_id, challengee_id, _, _, _, _, _ = active
        await self.invalidate_duel(ctx, duelid, challenger_id, challengee_id)

    @ discord_common.send_error_if(DuelCogError)
    async def cog_command_error(self, ctx, error):
        pass


def setup(bot):
    bot.add_cog(Tournament(bot))
