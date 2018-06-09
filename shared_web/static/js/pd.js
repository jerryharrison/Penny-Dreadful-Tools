/*global PD:true Deckbox:false FooTable:false, moment:false, $, Tipped */
window.PD = {};
PD.init = function () {
    PD.initDismiss();
    PD.initMenu();
    PD.initTables();
    PD.initDetails();
    PD.initTooltips();
    $("input[type=file]").on("change", PD.loadDeck).on("change", PD.toggleDrawDropdown);
    $(".bugtable").trigger("sorton", [[[2,0],[0,0]]]);
    $(".toggle-illegal").on("change", PD.toggleIllegalCards);
    PD.localizeTimes();
    PD.initSignupDeckChooser();
    PD.initStatusFooter();
};
PD.initDismiss = function () {
    $(".dismiss").click(function () {
        $(this).closest(".intro-container").hide();
        $.post("/api/intro/"); // Fire and forget request to set cookie to remember dismissal of intro box and not show it again.
        return false;
    });
};
PD.initMenu = function () {
    $(".has-submenu").hoverIntent({
        over: PD.onDropdownHover,
        out: PD.onDropdownLeave,
        interval: 50,
        timeout: 250
    });
};
PD.onDropdownHover = function () {
    $(this).addClass("hovering");
    $(this).find(".submenu-container").slideDown("fast");
};
PD.onDropdownLeave = function () {
    $(this).removeClass("hovering");
    $(this).find(".submenu-container").slideUp("fast");
};
PD.initTables = function () {
    var selector = "main table";

    // Apply footable to all reasonably-sized tables for a nice mobile layout.
    $(selector).filter(function () { return $(this).find("> tbody > tr").length <= 1000; }).footable({
        "toggleColumn": "last",
        "breakpoints": {
            "xs": 359,
            "sm": 639,
            "md": 799,
            "lg": 1119
        }
    }).bind("sortStart", function () {
        // Prevent expanded information from sorting first and not staying with parent row by collapsing all expanded rows before sorting.
        FooTable.get(this).rows.collapse();
    }).css({ "display": "table" });
    $("div.loading").addClass("loaded");
    // This operation is very expensive on large tables so we show them on load by default despite it being less pretty.
    $(selector).not(".very-large").css({"visibility": "visible"});

    $.tablesorter.addParser({
        "id": "record",
        "is": function(s) {
            return s.match(/^\d+–\d+(–\d+)?$/);
        },
        "format": function(s) {
            var parts, wins, losses;
            if (s == "") {
                return "";
            }
            parts = s.split("–");
            wins = parseInt(parts[0]);
            losses = parseInt(parts[1]);
            return ((wins - losses) * 1000 + wins).toString();
        },
        "type": "numeric"
    });
    $.tablesorter.addParser({
        "id": "colors",
        "is": function(_s, _table, _td, $td) {
            return $td.find("span.mana").length > 0;
        },
        "format": function(_s, _table, td) {
            var i,
                score = 0,
                symbols = ["_", "W", "U", "B", "R", "G"];
            for (i = 0; i < symbols.length; i++) {
                if ($(td).find("span.mana-" + symbols[i]).length > 0) {
                    score += Math.pow(i, 10);
                }
            }
            return score;
        },
        "type": "numeric"
    });
    PD.bugCategories = ["Game Breaking", "Avoidable Game Breaking", "Advantageous", "Disadvantageous", "Graphical", "Non-Functional ability", "Unclassified"];
    $.tablesorter.addParser({
        "id": "bugseverity",
        "is": function(s) {
            return PD.bugCategories.indexOf(s) > -1;
        },
        "format": function(s) {
            return PD.bugCategories.indexOf(s);
        },
        "type": "numeric"
    });
    $.tablesorter.addParser({
        "id": "archetype",
        is: function (_s, _table, _td, $td) {
            return $td.hasClass("initial");
        },
        "format": function(s, table, td) {
            return $(td).data("sort");
        },
        "type": "numeric"
    })
    /* Give archetype columns the classes primary and secondary so that we can nest when sorted by first column but not otherwise. */
    $("table.archetypes").tablesorter({
        "sortList": [[0, 0]],
        "widgets": ["columns"],
        "widgetOptions": {"columns" : ["primary", "secondary"]}
    });
    $(selector).tablesorter({});
};
PD.initDetails = function () {
    $(".details").siblings("p.question").click(function () {
        $(this).siblings(".details").toggle();
        return false;
    });
};
// Disable tooltips on touch devices where they are awkward but enable on others where they are useful.
PD.initTooltips = function () {
    $("body").on("touchstart", function() {
        $("body").off();
    });
    $("body").on("mouseover", function() {
        if (typeof Deckbox != "undefined") {
            Deckbox._.enable();
        }
        Tipped.create("main [title]", {"showDelay": 500, "size": "large", maxWidth: "200"});
        $("body").off();
    });
};
PD.loadDeck = function () {
    var file = this.files[0],
        reader = new FileReader();
    reader.onload = function (e) {
        $("textarea").val(e.target.result);
    };
    reader.readAsText(file);
};
PD.toggleDrawDropdown = function () {
    var can_draw = false;
    $(document).find(".deckselect").each(function(_, select) {
        can_draw = can_draw || select.selectedOptions[0].classList.contains("deck-can-draw");
    });
    if (can_draw) {
        $(".draw-report").css("visibility", "visible");
    }
    else {
        $(".draw-report").css("visibility", "hidden");
        $("#draws").val(0);
    }
    return can_draw;
};
PD.toggleIllegalCards = function () {
    // Fix the width of the table columns so that it does not "jump" when rows are added or removed.
    $(".bugtable tr td").each(function() {
        $(this).css({"width": $(this).width() + "px"});
    });
    $(".bugtable").not(".footable-details").each(function () { FooTable.get(this).rows.collapse(); });
    $("tr").find(".illegal").closest("tr").toggle(!this.checked);
};
PD.localizeTimes = function () {
    PD.localizeTimeElements();
    PD.hideRepetitionInCalendar();
};
PD.localizeTimeElements = function () {
    $("time").each(function () {
        var t = moment($(this).attr("datetime")),
            format = $(this).data("format"),
            tz = moment.tz.guess(),
            s = t.tz(tz).format(format);
        $(this).html(s).show();
    });
};
PD.hideRepetitionInCalendar = function () {
    PD.hideRepetition(".calendar time.month");
    PD.hideRepetition(".calendar time.day");
};
PD.hideRepetition = function (selector) {
    var v;
    $(selector).each(function ()  {
        if ($(this).html() === v) {
            $(this).html("");
        } else {
            v = $(this).html();
        }
    });
};
PD.getUrlParams = function () {
    var vars = [], hash, i,
        hashes = window.location.href.slice(window.location.href.indexOf("?") + 1).split("&");
    for (i = 0; i < hashes.length; i++) {
        hash = hashes[i].split("=");
        vars.push(hash[0]);
        vars[hash[0]] = hash[1];
    }
    return vars;
};
PD.getUrlParam = function (name) {
    return PD.getUrlParams()[name];
};

PD.initSignupDeckChooser = function () {
    $("#signup_recent_decks").on("change", function() {
        var data = JSON.parse($("option:selected", this).attr("data"));
        $("#name").val(data.name);
        var textarea = $("#decklist");
        var buffer = data.main.join("\n") + "\n";
        if (data.sb.length > 0) {
            buffer += "\nSideboard:\n" + data.sb.join("\n");
        }
        textarea.val(buffer);
    })
};

PD.initStatusFooter = function() {
    $.get("/api/status/", function(data) {
        var text = "";
        if (data.discord_id) {
            text += "You are logged in";
            if (data.mtgo_username != null) {
                text += " as <a href=\"/people/" + PD.htmlEscape(data.mtgo_username) + "\">" + PD.htmlEscape(data.mtgo_username) + "</a>";
            } else {
                text += " <span class=\"division\"></span> <a href=\"/link/\">Link</a> your Magic Online account";
            }
            if (data.deck) {
                text += " <span class=\"division\"></span> " + data.deck.wins + "–" + data.deck.losses + " with <a href=\"" + PD.htmlEscape(data.deck.url) + "\">" + PD.htmlEscape(data.deck.name) + "</a> <span class=\"division\"></span> <a href=\"/retire/\">Retire</a>";
            } else if (data.mtgo_username != null) {
                text += " <span class=\"division\"></span> You do not have an active league run — <a href=\"/signup/\">Sign Up</a>";
            }
            text += " <span class=\"division\"></span> <a href=\"/logout/\">Log Out</a>";
        } else  {
            text += "<a href=\"/authenticate/?target=" + window.location.href + "\">Log In</a>";
        }
        $(".status-bar").html("<p>" + text + "</p>");
        if (data.admin) {
            $(".admin").show();
            if (data.archetypes_to_tag > 0) {
                $('.edit_archetypes').children()[0].text = data.archetypes_to_tag
            }
        }
        if (!data.hide_intro && !PD.getUrlParam("hide_intro")) {
            $(".intro-container").show();
        }
    })
};

PD.htmlEscape = function (s) {
    return $("<div>").text(s).html();
};

$(document).ready(function () {
    PD.init();
});
