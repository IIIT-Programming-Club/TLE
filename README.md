# TLE @ IIITH
TLE is a Discord bot centered around Competitive Programming customized for IIITH Programing Club. Based on the [TLE bot](https://github.com/cheran-senthil/TLE).

## Features
The features of the bot are split into a number of cogs, each handling their own set of commands.

### Codeforces cogs
- **Codeforces** Commands that can recommend problems or contests to users, taking their rating into account.
- **Contests** Shows details of upcoming/running contests.
- **Graphs** Plots various data gathered from Codeforces, e.g. rating distributions and user problem statistics.
- **Handles** Gets or sets information about a specific user's Codeforces handle, or shows a list of Codeforces handles.

### CSES cog
- **CSES** Commands related to the [CSES problemset](https://cses.fi/problemset/), such as showing leaderboards.

### Tournament cog
- **Tournament** Commands related to dueling tournaments. Uses the wrapper [Achallonge](https://achallonge.readthedocs.io/) for challonge API to handle tournaments.

### Other cogs
- **Starboard** Commands related to the starboard, which adds the message to starboard when the author reacts their message with a ⭐️. Used to keep track of open doubts.
- **CacheControl** Commands related to data caching.


## Installation
Clone the repository
```bash
git clone https://github.com/Groverkss/TLE
```

> :warning: **TLE requires Python 3.7 or later!**

TLE depends on cairo and pango for graphics and text rendering, which you need
to install through your package manager. For Ubuntu, the relevant packages
can be installed with

```bash
apt-get install libcairo2-dev libgirepository1.0-dev libpango1.0-dev pkg-config python3-dev gir1.2-pango-1.0
```

---

Create a virtual environment to manage dependencies. If you are using `apt` 
you can use the following command to install venv.

```bash
apt install python3-venv
```

Create a virtual environment and install the required packages from requirements.txt

```bash
python -m venv .env
source .env/bin/activate
pip3 install -r requirements.txt
```

---

You will need to setup a bot on your server before continuing, follow the
directions [here](https://github.com/reactiflux/discord-irc/wiki/Creating-a-discord-bot-&-getting-a-token).
Following this, you should have your bot appearing in your server and you should have the Discord bot token.
Finally, go to the `Bot` settings in your App's Developer Portal (in the same page where you copied your Bot Token)
and enable the `Server Members Intent`.

To start TLE export the token and the bot prefix as an environment variable. 
These can be placed in a file `secrets` in the base folder and the `run.sh`
will automatically pick them up.

Make sure the `secrets` file has execute permission.

Add the following lines in your `secrets`:

```bash
export BOT_TOKEN="<BOT_TOKEN_FROM_DISCORD_CONSOLE>"
export BOT_PREFIX="<BOT_PREFIX_TO_BE_USED>"
```
If you want to use the tournament features, you need to create an account on
[challonge](https://challonge.com/) and export the username and api as follows

```bash
export CHALLONGE_USERNAME="<CHALLONGE_USERNAME>"
export CHALLONGE_API="<CHALLONGE_API>"
```

and run

```
./run.sh
```

### Notes
 - In order to run admin-only commands, you need to have the `Admin` role, which needs to be created in your Discord server and assign it to yourself/other administrators.
 - In order to prevent the bot suggesting an author's problems to the author, a python file needs to be run (since this can not be done through the Codeforces API) which will save the authors for specific contests to a file. To do this run `python extra/scrape_cf_contest_writers.py` which will generate a JSON file that should be placed in the `data/misc/` folder.
 - In order to display CJK (East Asian) characters for usernames, we need appropriate fonts. Their size is ~36MB, so we don't keep in the repo itself and it is gitignored. They will be downloaded automatically when the bot is run if not already present.
 - One of the bot's features is to assign roles to users based on their rating on Codeforces. In order for this functionality to work properly, the following roles need to exist in your Discord server
     - Newbie
     - Pupil
     - Specialist
     - Expert
     - Candidate Master
     - Master
     - International Master
     - Grandmaster
     - International Grandmaster
     - Legendary Grandmaster

## Usage
In order to run bot commands you can either ping the bot at the beginning of the command or prefix the command with the BOT_PREFIX (for examples, lets assume BOT_PREFIX = ';'), e.g. `;handle pretty`.

In order to find available commands, you can run `;help` which will bring a list of commands/groups of commands which are available. To get more details about a specific command you can type `;help <command-name>`.

## Contributing
Pull requests are welcome. For major changes please open an issue first to discuss what you would like to change.

Before submitting your PR, consider running some code formatter on the lines you touched or added. This will help reduce the time spent on fixing small styling issues in code review. 
`Black` codeformatter is recommended. [Black](https://black.readthedocs.io/en/stable/)

Please refrain from formatting the whole file if you just change some small part of it. If you feel the need to tidy up some particularly egregious code, then do that in a separate PR.

## License
[MIT](https://choosealicense.com/licenses/mit/)
