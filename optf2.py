#!/usr/bin/env python

"""
Copyright (c) 2010, Anthony Garcia <lagg@lavabit.com>

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
"""

try:
    import steam.user, steam.tf2, steam, os, json, urllib2
    from time import time
    import cPickle as pickle
    from cStringIO import StringIO
    import web
    from web import form
    from copy import deepcopy
except ImportError as E:
    print(str(E))
    raise SystemExit

# Configuration stuff

# You probably want this to be
# an absolute path if you're not running the built-in server
template_dir = "templates/"

# Most links to other viewer pages will
# be prefixed with this.
virtual_root = "/"

css_url = "/static/style.css"

# The url to prefix URLs
# pointing to static data with
# e.g. class icons
static_prefix = "/static/"

api_key = None

language = "en"

# It would be nice of you not to change this
product_name = "OPTF2"

# Where to get the source code.
source_url = "http://gitorious.org/steamodd/optf2"

# Cache a player's backpack. Reduces the number of API
# requests and makes it a lot faster but might make the
# database big
cache_pack = True

# Refresh cache every x seconds.
cache_pack_refresh_interval = 30

# How many rows to show for the top viewed backpacks table
top_backpack_rows = 10

# Turn on debugging (prints a backtrace and other info
# instead of returning an internal server error)
web.config.debug = False

# Enables fastcgi support with flup, be sure to have it
# installed.
enable_fastcgi = False

# These stop the script name from showing up
# in URLs after a redirect. Remove them
# if they cause problems.
os.environ["SCRIPT_NAME"] = ''
os.environ["REAL_SCRIPT_NAME"] = ''

# The link to the news page/changelog
# set this to None if you don't want
# this shown. (Not recommended)
news_url = "http://agg.optf2.com/log/?cat=5"

# The max size of the backpack. Used
# for the padded cell sort
backpack_padded_size = 200

# End of configuration stuff

urls = (
    virtual_root + "comp/(.+)", "user_completion",
    virtual_root + "user/(.*)", "pack_fetch",
    virtual_root + "feed/(.+)", "pack_feed",
    virtual_root + "item/(.+)", "pack_item",
    virtual_root + "persona/(.+)", "persona",
    virtual_root + "schema_dump", "schema_dump",
    virtual_root + "about", "about",
    virtual_root, "index"
    )

# The 64 bit ID of the Valve group (this is how I check
# if the user is a Valve employee)
valve_group_id = 103582791429521412

qualitydict = {"unique": "The ", "community": "Community ",
               "developer": "Legendary ", "normal": "",
               "selfmade": "My ", "vintage": "Vintage ",
               "rarity4": "Unusual "}

# I don't like this either but Valve didn't expose them
# through the API
particledict = {0: "Invalid Particle",
                1: "Particle 1",
                2: "Flying Bits",
                3: "Nemesis Burst",
                4: "Community Sparkle",
                5: "Holy Glow",
                6: "Green Confetti",
                7: "Purple Confetti",
                8: "Haunted Ghosts",
                9: "Green Energy",
                10: "Purple Energy",
                11: "Circling TF Logo",
                12: "Massed Flies",
                13: "Burning Flames",
                14: "Scorching Flames",
                15: "Searing Plasma",
                16: "Vivid Plasma",
                17: "Sunbeams",
                18: "Circling Peace Sign",
                19: "Circling Heart"}

# These should stay explicit
render_globals = {"css_url": css_url,
                  "virtual_root": virtual_root,
                  "static_prefix": static_prefix,
                  "encode_url": web.urlquote,
                  "len": len,
                  "qualitydict": qualitydict,
                  "particledict": particledict,
                  "instance": web.ctx,
                  "product_name": product_name,
                  "source_url": source_url,
                  "wiki_url": "http://wiki.teamfortress.com/wiki/",
                  "news_url": news_url,
                  "qurl": web.http.changequery
                  }

app = web.application(urls, globals())
templates = web.template.render(template_dir, base = "base",
                                globals = render_globals)

steam.set_api_key(api_key)
steam.set_language(language)

db_schema = ["CREATE TABLE IF NOT EXISTS search_count (id64 INTEGER, ip TEXT, count INTEGER DEFAULT 1)",
             "CREATE TABLE IF NOT EXISTS backpack_cache (id64 INTEGER PRIMARY KEY, backpack BLOB, last_refresh DATE)",
             "CREATE TABLE IF NOT EXISTS profile_cache (id64 INTEGER PRIMARY KEY, profile BLOB, last_refresh DATE)",
             "CREATE TABLE IF NOT EXISTS unique_views (id64 INTEGER PRIMARY KEY, count INTEGER DEFAULT 1, persona TEXT, valve BOOLEAN)"]
db_obj = web.database(dbn = "sqlite", db = os.path.join(steam.get_cache_dir(), "optf2.db"))
for s in db_schema:
    db_obj.query(s)

def cache_not_stale(row):
    return (int(time()) - row["last_refresh"]) < cache_pack_refresh_interval

def refresh_profile_cache(sid):
    user = steam.user.profile(sid)
    summary = user.get_summary_object()

    try:
        db_obj.insert("profile_cache", id64 = user.get_id64(),
                      last_refresh = int(time()),
                      profile = pickle.dumps(summary))
    except:
        db_obj.update("profile_cache", id64 = user.get_id64(),
                      last_refresh = int(time()),
                      profile = pickle.dumps(summary),
                      where = "id64 = $id64", vars = {"id64": user.get_id64()})

    return user

def load_profile_cached(sid, stale = False):
    user = steam.user.profile()
    if not sid.isdigit():
        sid = user.get_id64_from_sid(sid.encode("ascii"))
        if not sid:
            return refresh_profile_cache(sid)

    if cache_pack:
        try:
            prow = db_obj.select("profile_cache", what = "profile, last_refresh",
                                 where = "id64 = $id64", vars = {"id64": int(sid)})[0]
            pfile = StringIO(str(prow["profile"]))

            if stale or cache_not_stale(prow):
                user.load_summary_file(pfile)
            else:
                try:
                    return refresh_profile_cache(sid)
                except:
                    user.load_summary_file(pfile)
                    return user
            return user
        except IndexError:
            return refresh_profile_cache(sid)
    else:
        return refresh_profile_cache(sid)

def refresh_pack_cache(user, pack):
    pack.load_pack(user)
    try:
        db_obj.insert("backpack_cache", id64 = user.get_id64(), last_refresh = int(time()),
                      backpack = pickle.dumps(pack.get_pack_object()))
    except:
        db_obj.update("backpack_cache", where = "id64 = $id64", vars = {"id64": user.get_id64()},
                      last_refresh = int(time()),
                      backpack = pickle.dumps(pack.get_pack_object()))

def load_pack_cached(user, pack, stale = False):
    if cache_pack:
        try:
            packrow = db_obj.select("backpack_cache", what = "backpack, last_refresh", where = "id64 = $uid64",
                                    vars = {"uid64": user.get_id64()})[0]
            packfile = StringIO(str(packrow["backpack"]))

            if stale or cache_not_stale(packrow):
                pack.load_pack_file(packfile)
            else:
                try:
                    refresh_pack_cache(user, pack)
                except urllib2.URLError:
                    pack.load_pack_file(packfile)
        except IndexError:
            refresh_pack_cache(user, pack)
    else:
        pack.load_pack(user)

def get_invalid_pos_items(items, pack):
    poslist = []
    invalid_items = []
    for item in items:
        if not item: continue
        pos = pack.get_item_position(item)
        if pos != -1 and pos not in poslist:
            poslist.append(pack.get_item_position(item))
        else:
            for item in items:
                if item and item not in invalid_items and pos == pack.get_item_position(item):
                    invalid_items.append(deepcopy(item))

    return invalid_items

def sort_items(items, pack, sortby):
    itemcmp = None
    def defcmp(x, y):
        if x < y:
            return -1
        elif x > y:
            return 1
        elif x == y:
            return 0

    if sortby == "serial":
        def itemcmp(x, y):
            return defcmp(pack.get_item_id(x),
                          pack.get_item_id(y))
    elif sortby == "cell":
        def itemcmp(x, y):
            return defcmp(pack.get_item_position(x),
                          pack.get_item_position(y))
    elif sortby == "level":
        def itemcmp(x, y):
            return defcmp(pack.get_item_level(x),
                          pack.get_item_level(y))
    elif sortby == "name":
        def itemcmp(x, y):
            return defcmp(pack.get_item_quality(x)["str"] + " " + pack.get_item_name(x),
                          pack.get_item_quality(y)["str"] + " " + pack.get_item_name(y))
    elif sortby == "slot":
        def itemcmp(x, y):
            return defcmp(pack.get_item_slot(x), pack.get_item_slot(y))
    elif sortby == "class":
        def itemcmp(x, y):
            cx = pack.get_item_equipable_classes(x)
            cy = pack.get_item_equipable_classes(y)
            lenx = len(cx)
            leny = len(cy)

            if lenx == 1 and leny == 1:
                return defcmp(cx[0], cy[0])
            else:
                return defcmp(lenx, leny)

    if itemcmp:
        items.sort(cmp = itemcmp)
        if sortby == "cell":
            newitems = []
            lastpos = -1
            for item in items:
                if lastpos == -1:
                    lastpos = pack.get_item_position(item)
                else:
                    for i in range(lastpos, pack.get_item_position(item) - 1):
                        newitems.append(None)
                newitems.append(deepcopy(item))
                lastpos = pack.get_item_position(item)
            if lastpos < backpack_padded_size:
                for i in range(lastpos, backpack_padded_size):
                    newitems.append(None)
            return newitems
    return items

def filter_items_by_class(items, pack, theclass):
    filtered_items = []

    for item in items:
        if not item: continue
        classes = pack.get_item_equipable_classes(item)
        for c in classes:
            if c == theclass:
                filtered_items.append(item)
                break
    return filtered_items

def process_attributes(items, pack):
    """ Filters attributes for the item list,
    optf2-specific keys are prefixed with optf2_ """

    for item in items:
        if not item: continue
        attrs = pack.get_item_attributes(item)
        item["optf2_untradeable"] = pack.is_item_untradeable(item)
        item["optf2_attrs"] = []
        item["optf2_description"] = pack.get_item_custom_description(item)

        for attr in attrs:
            desc = pack.get_attribute_description(attr)

            if pack.get_attribute_name(attr) == "always tradable":
                continue

            if pack.get_attribute_name(attr) == "cannot trade":
                item["optf2_untradeable"] = True
                continue

            if desc.find("Attrib_") != -1:
                continue

            # Another bogus description string
            if pack.get_attribute_name(attr) == "noise maker":
                continue

            # Workaround until Valve gives sane values
            if (pack.get_attribute_value_type(attr) != "date" and
                attr["value"] > 1000000000 and
                "float_value" in attr):
                attr["value"] = attr["float_value"]

            # Contained item is a schema id
            if pack.get_attribute_name(attr) == "referenced item def":
                sival = int(pack.get_attribute_value(attr))
                sitem = pack.get_item_by_schema_id(sival)
                sidesc = "an invalid item"

                if item:
                    sidesc = '<a href="{0}item/from_schema/{1:d}">{2}</a>'.format(virtual_root, sival, pack.get_item_name(sitem))
                attr["description_string"] = 'Contains ' + sidesc

            # The minicrit attribute has the dalokohs bar
            # description string
            if pack.get_attribute_name(attr) == "lunchbox adds minicrits":
                attr["description_string"] = "While under the effects, damage done and damage taken will be Mini-Crits."

            # The GRU have the crit-o-cola mini-crit
            # attribute attached for some reason.
            if (pack.get_item_schema_id(item) == 239 and
                pack.get_attribute_name(attr) == "lunchbox adds minicrits"):
                continue

            if pack.get_attribute_name(attr) == "set item tint RGB":
                if attr.has_key("float_value") and pack.get_item_class(item) != "tool":
                    raw_rgb = int(attr["float_value"])
                else:
                    raw_rgb = int(pack.get_attribute_value(attr))
                item_color = "#{0:X}{1:X}{2:X}".format((raw_rgb >> 16) & 0xFF,
                                                        (raw_rgb >> 8) & 0xFF,
                                                        (raw_rgb) & 0xFF)
                item["optf2_color"] = item_color
                continue

            if pack.get_attribute_name(attr) == "attach particle effect":
                attr["description_string"] = ("Effect: " +
                                              particledict.get(int(attr["value"]), particledict[0]))

            if pack.get_attribute_name(attr) == "gifter account id":
                attr["description_string"] = "Gift"
                item["optf2_gift_from"] = "7656" + str(int(pack.get_attribute_value(attr) +
                                                           1197960265728))
                try:
                    user = load_profile_cached(item["optf2_gift_from"], stale = True)
                    item["optf2_gift_from_persona"] = user.get_persona()
                except:
                    item["optf2_gift_from_persona"] = "this user"

            attr["description_string"] = attr["description_string"].replace("\n", "<br/>")
            item["optf2_attrs"].append(deepcopy(attr))

        quality_str = pack.get_item_quality(item)["str"]
        pretty_quality_str = pack.get_item_quality(item)["prettystr"]
        prefix = qualitydict.get(quality_str, "")
        custom_name = pack.get_item_custom_name(item)
        item_name = pack.get_item_name(item)

        if item_name.find("The ") != -1 and pack.is_item_prefixed(item):
            item_name = item_name[4:]

        if custom_name or (not pack.is_item_prefixed(item) and quality_str == "unique"):
            prefix = ""
        if custom_name:
            item_name = custom_name

        item["optf2_cell_name"] = '<div class="{0}_name">{1} {2}</div>'.format(
            quality_str, prefix, item_name)

        if custom_name or (not pack.is_item_prefixed(item) and quality_str == "unique"):
            prefix = ""
        else:
            prefix = pretty_quality_str
        color = item.get("optf2_color")
        paint_job = ""
        if color:
            paint_job = '<span style="color: {0}; font-weight: bold;">Painted</span>'.format(color)
        item["optf2_dedicated_name"] = "{0} {1} {2}".format(paint_job, prefix, item_name)

        if color:
            paint_job = "Painted"
        item["optf2_title_name"] = "{0} {1} {2}".format(paint_job, prefix, item_name)

        if color:
            paint_job = "(Painted)"
        else:
            paint_job = ""
        if prefix:
            prefix = qualitydict.get(quality_str, pretty_quality_str)

        item["optf2_feed_name"] = "{0} {1} {2}".format(prefix, item_name, paint_job)

    return items

def get_equippable_classes(items, pack):
    """ Returns a set of classes that can equip this
    item """

    valid_classes = set()

    for item in items:
        if not item: continue
        classes = pack.get_item_equipable_classes(item)
        if classes[0]: valid_classes |= set(classes)

    return valid_classes

class schema_dump:
    """ Dumps everything in the schema in a pretty way """

    def GET(self):
        try:
            query = web.input()
            pack = steam.tf2.backpack()
            items = pack.get_items(from_schema = True)

            if "sortclass" in query:
                items = filter_items_by_class(items, pack, query["sortclass"])

            filter_classes = get_equippable_classes(items, pack)

            return templates.schema_dump(pack, process_attributes(items, pack), filter_classes)
        except:
            return templates.error("Couldn't load schema")

class user_completion:
    """ Searches for an account matching the username given in the query
    and returns a JSON object
    Yes it's dirty, yes it'll probably die if Valve changes the layout.
    Yes it's Valve's fault for not providing an equivalent API call.
    Yes I can't use minidom because I would have to replace unicode chars
    because of Valve's lazy encoding.
    Yes I'm designing it to be reusable by other people and myself. """

    _community_url = "http://steamcommunity.com/"
    def GET(self, user):
        search_url = self._community_url + "actions/Search?T=Account&K={0}".format(web.urlquote(user))

        try:
            res = urllib2.urlopen(search_url).read().split('<a class="linkTitle" href="')
            userlist = []

            for user in res:
                if user.startswith(self._community_url):
                    userobj = {
                        "persona": user[user.find(">") + 1:user.find("<")],
                        "id": os.path.basename(user[:user.find('"')])
                        }
                    if user.startswith(self._community_url + "profiles"):
                        userobj["id_type"] = "id64"
                    else:
                        userobj["id_type"] = "id"
                    userlist.append(userobj)
            return json.dumps(userlist)
        except:
            return "{}"

class pack_item:
    def GET(self, iid):
        def item_get(idl):
            if idl[0] == "from_schema":
                item = pack.get_item_by_schema_id(int(idl[1]))
            else:
                item = pack.get_item_by_id(int(idl[1]))
                if not item:
                    try: refresh_pack_cache(user, pack)
                    except urllib2.URLError: pass
                item = pack.get_item_by_id(int(idl[1]))

            if not item:
                raise Exception("Item not found")
            return item

        try:
            idl = iid.split('/')
            pack = steam.tf2.backpack()
            if idl[0] != "from_schema":
                user = load_profile_cached(idl[0], stale = True)
                load_pack_cached(user, pack, stale = True)
            else:
                user = None

            try: idl[1] = int(idl[1])
            except: raise Exception("Item ID must be an integer")

            item = process_attributes([item_get(idl)], pack)[0]
        except Exception as E:
            return templates.error(str(E))
        return templates.item(user, item, pack)

class persona:
    def GET(self, id):
        theobject = {"persona": "", "realname": ""}
        callback = web.input().get("jsonp")

        try:
            user = steam.user.profile(id)
            theobject["persona"] = user.get_persona()
            theobject["realname"] = user.get_real_name()
            theobject["id64"] = str(user.get_id64())
            theobject["avatarurl"] = user.get_avatar_url(user.AVATAR_SMALL)
        except: pass

        web.header("Content-Type", "text/javascript")
        if not callback:
            return json.dumps(theobject)
        else:
            return callback + '(' + json.dumps(theobject) + ');'

class about:
    def GET(self):
        return templates.about()

class pack_fetch:
    def _get_page_for_sid(self, sid):
        if not sid:
            return templates.error("Need an ID")
        try:
            user = load_profile_cached(sid)
        except steam.user.ProfileError:
            search = json.loads(user_completion().GET(sid))
            nuser = None
            for result in search:
                if result["persona"] == sid:
                    nuser = result["id"]
                    break
            for result in search:
                if result["persona"].lower() == sid.lower():
                    nuser = result["id"]
                    break
            for result in search:
                if result["persona"].lower().find(sid.lower()) != -1:
                    nuser = result["id"]
                    break
            if nuser:
                try:
                    user = load_profile_cached(nuser)
                except:
                    return templates.error("Failed to load user profile")
            else:
                return templates.error("Bad profile name")

        pack = steam.tf2.backpack()
        query = web.input()
        sortby = query.get("sort", "default")

        try:
            load_pack_cached(user, pack)

            items = pack.get_items()

            items = sort_items(items, pack, sortby)

            if "sortclass" in query:
                items = filter_items_by_class(items, pack, query["sortclass"])

            process_attributes(items, pack)

            filter_classes = get_equippable_classes(items, pack)

            baditems = get_invalid_pos_items(items, pack)
            for bitem in baditems:
                if bitem in items:
                    items.remove(bitem)
        except:
            return templates.error("Failed to load backpack")

        isvalve = (user.get_primary_group() == valve_group_id)
        count = 1
        try:
            count = db_obj.select("search_count", where = "id64 = $id64 AND ip = $ip",
                                  vars = {"id64": user.get_id64(),
                                          "ip": web.ctx.ip})[0]["count"]

            db_obj.query("""UPDATE search_count SET count = count + 1
                                                    WHERE id64 = $id64 AND ip = $ip """,
                         vars = {"id64": user.get_id64(), "ip": web.ctx.ip})
        except:
            db_obj.insert("search_count", id64 = user.get_id64(),
                          ip = web.ctx.ip)

        try:
            views = db_obj.query("SELECT COUNT(*) AS unique_views FROM search_count WHERE id64 = $id64",
                                 vars = {"id64": user.get_id64()})[0]["unique_views"]
        except:
            views = 1

        try:
            db_obj.insert("unique_views", id64 = user.get_id64(),
                          persona = user.get_persona(), valve = isvalve,
                          count = views)
        except:
            db_obj.update("unique_views", where = "id64 = $id64",
                          vars = {"id64": user.get_id64()},
                          persona = user.get_persona(), valve = isvalve,
                          count = views)

        return templates.inventory(user, pack, isvalve, items, views, filter_classes, sortby, baditems)

    def GET(self, sid):
        return self._get_page_for_sid(sid)

class pack_feed:
    def GET(self, sid):
        try:
            user = load_profile_cached(sid, stale = True)
            pack = steam.tf2.backpack()
            load_pack_cached(user, pack)
            items = pack.get_items()
            process_attributes(items, pack)
        except Exception as E:
            return templates.error(str(E))
        web.header("Content-Type", "application/rss+xml")
        return web.template.render(template_dir,
                                   globals = render_globals).inventory_feed(user,
                                                                            pack,
                                                                            items)

class index:
    def GET(self):
        profile_form = form.Form(
            form.Textbox("User"),
            form.Button("View")
            )
        countlist = db_obj.select("unique_views", order = "count DESC", limit = top_backpack_rows)
        return templates.index(profile_form(), countlist)
    def POST(self):
        user = web.input().get("User")
        if user: raise web.seeother(virtual_root + "user/" + os.path.basename(user))
        else: return templates.error("Don't do that")

if enable_fastcgi:
    web.wsgi.runwsgi = lambda func, addr=None: web.wsgi.runfcgi(func, addr)

if __name__ == "__main__":
    app.run()