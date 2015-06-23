/*global define*/
/**
 * To load this extension, add the following to your custom.js:
 *
 * require(['base/js/events'], function (events) {
 *     events.on('app_initialized.NotebookApp', function() {
 *         IPython.load_extensions('nbgrader');
 *     });
 * });
 *
**/

define([
    'require',
    'jquery',
    'base/js/namespace',
    'base/js/dialog',
    'notebook/js/celltoolbar',
    'base/js/events'

], function (require, $, IPython, dialog, celltoolbar, events) {
    "use strict";

    var nbgrader_preset_name = "Create Assignment";
    var nbgrader_cls = "nbgrader-cell";
    var warning;

    var CellToolbar = celltoolbar.CellToolbar;

    // trigger an event when the toolbar is being rebuilt
    CellToolbar.prototype._rebuild = CellToolbar.prototype.rebuild;
    CellToolbar.prototype.rebuild = function () {
        events.trigger('toolbar_rebuild.CellToolbar', this.cell);
        this._rebuild();
    };

    // trigger an event when the toolbar is being (globally) hidden
    CellToolbar._global_hide = CellToolbar.global_hide;
    CellToolbar.global_hide = function () {
        $("#nbgrader-total-points-group").hide();

        CellToolbar._global_hide();
        for (var i=0; i < CellToolbar._instances.length; i++) {
            events.trigger('global_hide.CellToolbar', CellToolbar._instances[i].cell);
        }
    };

    // show the total points when the preset is activated
    events.on('preset_activated.CellToolbar', function(evt, preset) {
        var elem = $("#nbgrader-total-points-group");
        if (preset.name === nbgrader_preset_name) {
            if (elem.length == 0) {
                elem = $("<div />").attr("id", "nbgrader-total-points-group");
                elem.addClass("btn-group");
                elem.append($("<span />").text("Total points:"));
                elem.append($("<input />")
                            .attr("disabled", "disabled")
                            .attr("type", "number")
                            .attr("id", "nbgrader-total-points"));
                $("#maintoolbar-container").append(elem);
            }
            elem.show();
            update_total();
        } else {
            elem.hide();
        }
    });

    // remove nbgrader class when the cell is either hidden or rebuilt
    events.on("global_hide.CellToolbar toolbar_rebuild.CellToolbar", function (evt, cell) {
        if (cell.element && cell.element.hasClass(nbgrader_cls)) {
            cell.element.removeClass(nbgrader_cls);
        }
    });

    // update total points when a cell is deleted
    events.on("delete.Cell", function (evt, info) {
        update_total();
    });

    var to_float = function(val) {
        if (val === undefined || val === "") {
            return 0;
        }
        return parseFloat(val);
    };

    var update_total = function() {
        var total_points = 0;
        var cells = IPython.notebook.get_cells();
        for (var i=0; i < cells.length; i++) {
            if (is_grade(cells[i])) {
                total_points += to_float(cells[i].metadata.nbgrader.points);
            }
        }
        $("#nbgrader-total-points").attr("value", total_points);
    };

    var validate_ids = function() {
        var elems, set, i, label;

        if (warning !== undefined) {
            return;
        }

        elems = $(".nbgrader-id-input");
        set = new Object();
        for (i = 0; i < elems.length; i++) {
            label = $(elems[i]).val();
            if (label in set) {
                warning = dialog.modal({
                    notebook: IPython.notebook,
                    keyboard_manager: IPython.keyboard_manager,
                    title: "Duplicate grade cell ID",
                    body: "The ID \"" + label + "\" has been used for more than one grade cell. This will cause nbgrader to break! Please make sure all grade cells have unique ids.",
                    buttons: {
                        OK: {
                            class: "btn-primary",
                            click: function () {
                                warning = undefined;
                            }
                        }
                    }
                });
            } else {
                set[label] = true;
            }
        }
    };

    /**
     * Is the cell a solution cell?
     */
    var is_solution = function (cell) {
        if (cell.metadata.nbgrader === undefined) {
            return false;
        } else if (cell.metadata.nbgrader.solution === undefined) {
            return false;
        } else {
            return cell.metadata.nbgrader.solution;
        }
    };

    /**
     * Set whether this cell is or is not a solution cell.
     */
    var set_solution = function (cell, val) {
        if (cell.metadata.nbgrader === undefined) {
            cell.metadata.nbgrader = {};
        }
        cell.metadata.nbgrader.solution = val;
    };

    /**
     * Is the cell a grade cell?
     */
    var is_grade = function (cell) {
        if (cell.metadata.nbgrader === undefined) {
            return false;
        } else if (cell.metadata.nbgrader.grade === undefined) {
            return false;
        } else {
            return cell.metadata.nbgrader.grade;
        }
    };

    /**
     * Set whether this cell is or is not a grade cell.
     */
    var set_grade = function (cell, val) {
        if (cell.metadata.nbgrader === undefined) {
            cell.metadata.nbgrader = {};
        }
        cell.metadata.nbgrader.grade = val;
    };

    var get_points = function (cell) {
        if (cell.metadata.nbgrader === undefined) {
            return 0;
        } else {
            return to_float(cell.metadata.nbgrader.points);
        }
    };

    var set_points = function (cell, val) {
        if (cell.metadata.nbgrader === undefined) {
            cell.metadata.nbgrader = {};
        }
        cell.metadata.nbgrader.points = to_float(val);
    };

    var get_grade_id = function (cell) {
        if (cell.metadata.nbgrader === undefined) {
            return '';
        } else if (cell.metadata.nbgrader.grade_id === undefined) {
            return '';
        } else {
            return cell.metadata.nbgrader.grade_id;
        }
    };

    var set_grade_id = function (cell, val) {
        if (cell.metadata.nbgrader === undefined) {
            cell.metadata.nbgrader = {};
        }
        if (val === undefined) {
            cell.metadata.nbgrader.grade_id = '';
        } else {
            cell.metadata.nbgrader.grade_id = val;
        }
    };

    /**
     * Add a display class to the cell element, depending on the
     * nbgrader cell type.
     */
    var display_cell = function (cell) {
        if (cell.element && (is_grade(cell) || is_solution(cell)) && !cell.element.hasClass(nbgrader_cls)) {
            cell.element.addClass(nbgrader_cls);
        }
    };

    var create_celltype_select = function (div, cell, celltoolbar) {
        // hack -- the DOM element for the celltoolbar is created before the
        // cell type is actually set, so we need to wait until the cell type
        // has been set before we can actually create the select menu
        if (cell.cell_type === null) {
            setTimeout(function () {
                create_celltype_select(div, cell, celltoolbar);
            }, 100);

        } else {

            var options_list = [];
            options_list.push(["-", ""]);
            options_list.push(["Manually graded answer", "manual"]);
            if (cell.cell_type == "code") {
                options_list.push(["Autograded answer", "solution"]);
                options_list.push(["Autograder tests", "tests"]);
            }

            var setter = function (cell, val) {
                if (val === "") {
                    set_solution(cell, false);
                    set_grade(cell, false);
                } else if (val === "manual") {
                    set_solution(cell, true);
                    set_grade(cell, true);
                } else if (val === "solution") {
                    set_solution(cell, true);
                    set_grade(cell, false);
                } else if (val === "tests") {
                    set_solution(cell, false);
                    set_grade(cell, true);
                } else {
                    throw new Error("invalid nbgrader cell type: " + val);
                }
            };

            var getter = function (cell) {
                if (is_solution(cell) && is_grade(cell)) {
                    return "manual";
                } else if (is_solution(cell) && cell.cell_type === "code") {
                    return "solution";
                } else if (is_grade(cell) && cell.cell_type === "code") {
                    return "tests";
                } else {
                    return "";
                }
            };

            var select = $('<select/>');
            for(var i=0; i < options_list.length; i++){
                var opt = $('<option/>')
                    .attr('value', options_list[i][1])
                    .text(options_list[i][0]);
                select.append(opt);
            }
            select.val(getter(cell));
            select.change(function () {
                setter(cell, select.val());
                celltoolbar.rebuild();
                update_total();
                display_cell(cell);
                validate_ids();
            });
            display_cell(cell);
            $(div).append($('<span/>').append(select));
        }
    };

    /**
     * Create the input text box for the problem or test id.
     */
    var create_id_input = function (div, cell, celltoolbar) {
        if (!is_grade(cell) && !is_solution(cell)) {
            return;
        }

        var local_div = $('<div/>');
        var text = $('<input/>').attr('type', 'text');
        var lbl = $('<label/>').append($('<span/>').text('ID: '));
        lbl.append(text);

        text.addClass('nbgrader-id-input');
        text.attr("value", get_grade_id(cell));
        validate_ids();
        text.change(function () {
            set_grade_id(cell, text.val());
            validate_ids();
        });

        local_div.addClass('nbgrader-id');
        $(div).append(local_div.append($('<span/>').append(lbl)));

        IPython.keyboard_manager.register_events(text);
    };

    /**
     * Create the input text box for the number of points the problem
     * is worth.
     */
    var create_points_input = function (div, cell, celltoolbar) {
        if (!is_grade(cell)) {
            return;
        }

        var local_div = $('<div/>');
        var text = $('<input/>').attr('type', 'number');
        var lbl = $('<label/>').append($('<span/>').text('Points: '));
        lbl.append(text);

        text.addClass('nbgrader-points-input');
        text.attr("value", get_points(cell));
        update_total();

        text.change(function () {
            set_points(cell, text.val());
            text.val(get_points(cell));
            update_total();
        });

        local_div.addClass('nbgrader-points');
        $(div).append(local_div.append($('<span/>').append(lbl)));

        IPython.keyboard_manager.register_events(text);
    };

    /**
     * Load custom css for the nbgrader toolbar.
     */
    var load_css = function () {
        var link = document.createElement('link');
        link.type = 'text/css';
        link.rel = 'stylesheet';
        link.href = require.toUrl('./nbgrader.css');
        document.getElementsByTagName('head')[0].appendChild(link);
    };

    /**
     * Load the nbgrader toolbar extension.
     */
    var load_extension = function () {
        load_css();
        CellToolbar.register_callback('create_assignment.grading_options', create_celltype_select);
        CellToolbar.register_callback('create_assignment.id_input', create_id_input);
        CellToolbar.register_callback('create_assignment.points_input', create_points_input);

        var preset = [
            'create_assignment.points_input',
            'create_assignment.id_input',
            'create_assignment.grading_options',
        ];
        CellToolbar.register_preset(nbgrader_preset_name, preset, IPython.notebook);
        console.log('nbgrader extension for metadata editing loaded.');
    };

    return {
        'load_ipython_extension': load_extension
    };
});
