/* SPDX-FileCopyrightText: 2025 Topias Silfverhuth
   SPDX-License-Identifier: MIT

   Shared chrome behaviour: theme switch and sidebar collapse.
   Both persist in localStorage; dark is the default when nothing is stored. */

(function () {
    "use strict";

    var root = document.documentElement;

    function store(key, value) {
        try { localStorage.setItem(key, value); } catch (e) { /* private mode */ }
    }

    function setTheme(theme) {
        root.dataset.theme = theme;
        store("theme", theme);
        var meta = document.querySelector('meta[name="theme-color"]');
        if (meta) {
            meta.setAttribute("content", theme === "light" ? "#f4f2ec" : "#0e1211");
        }
        // Charts repaint themselves against the new tokens.
        window.dispatchEvent(new CustomEvent("themechange", { detail: { theme: theme } }));
    }

    function toggleRail() {
        var collapsed = root.classList.toggle("rail-collapsed");
        store("railCollapsed", collapsed);
        var btn = document.getElementById("rail-btn");
        if (btn) {
            var label = collapsed ? "Expand sidebar" : "Collapse sidebar";
            btn.setAttribute("aria-label", label);
            btn.setAttribute("title", label);
        }
        window.dispatchEvent(new CustomEvent("railtoggle"));
    }

    function bind() {
        var themeBtn = document.getElementById("theme-btn");
        if (themeBtn && !themeBtn.dataset.bound) {
            themeBtn.dataset.bound = "1";
            themeBtn.addEventListener("click", function () {
                setTheme(root.dataset.theme === "light" ? "dark" : "light");
            });
        }

        var railBtn = document.getElementById("rail-btn");
        if (railBtn && !railBtn.dataset.bound) {
            railBtn.dataset.bound = "1";
            railBtn.addEventListener("click", toggleRail);
        }
    }

    // Read the current value of a CSS custom property (used for chart theming).
    window.cssVar = function (name) {
        return getComputedStyle(root).getPropertyValue(name).trim();
    };

    bind();
    document.addEventListener("DOMContentLoaded", bind);
    document.addEventListener("turbo:load", bind);
})();
