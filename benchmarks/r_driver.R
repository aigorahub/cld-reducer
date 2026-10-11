#!/usr/bin/env Rscript
# Development JSONL driver. See PROTOCOL.md. This file can also be sourced by tests.

bench_error <- function(message) {
  stop(structure(list(message = message, call = NULL),
                 class = c("benchmark_invalid_request", "error", "condition")))
}

bench_clock <- function() {
  precise <- requireNamespace("microbenchmark", quietly = TRUE)
  now <- if (precise) microbenchmark::get_nanotime else function() proc.time()[["elapsed"]] * 1e9
  # The first call can report platform precision limits. It is outside all timings.
  now()
  stamps <- vapply(seq_len(10000L), function(i) now(), numeric(1))
  deltas <- diff(stamps)
  positive <- deltas[deltas > 0]
  list(now = now, description = list(
    name = if (precise) "microbenchmark::get_nanotime" else "proc.time elapsed",
    monotonic = TRUE,
    resolution_ns = if (length(positive)) min(positive) else NULL,
    resolution_method = paste("Minimum positive delta of 10000 consecutive reads.",
                              "This includes clock call overhead and is an upper bound on resolution."),
    fallback = !precise,
    note = if (precise) "Platform monotonic timer; nanosecond units." else
      "proc.time elapsed has platform dependent resolution, commonly one millisecond."
  ))
}

bench_driver <- function(repo, presolve = "off") {
  if (!identical(presolve, "off")) bench_error("R supports --presolve off only")
  if (length(repo) != 1L || !grepl("^(/|[A-Za-z]:[/\\\\])", repo)) {
    bench_error("--repo must be an absolute source repository path")
  }
  repo <- normalizePath(repo, mustWork = TRUE)
  if (!file.exists(file.path(repo, "DESCRIPTION")) || !dir.exists(file.path(repo, "R"))) {
    bench_error("--repo must contain DESCRIPTION and R/")
  }
  clock <- bench_clock()
  now <- clock$now
  duration <- function(start) round(now() - start)
  state <- new.env(parent = emptyenv())
  state$runtime <- NULL
  state$version <- NULL

  load_runtime <- function() {
    if (!is.null(state$runtime)) return(invisible(NULL))
    started <- now()
    loadNamespace("Matrix")
    # Source functions, not an installed cldreducer. The private environment also
    # keeps capture hooks away from other package users in this R process.
    runtime <- new.env(parent = globalenv())
    files <- sort(list.files(file.path(repo, "R"), pattern = "\\.[Rr]$", full.names = TRUE))
    for (file in files) sys.source(file, envir = runtime, keep.source = FALSE)
    description <- read.dcf(file.path(repo, "DESCRIPTION"))
    module_load_ns <- duration(started)
    started <- now()
    loadNamespace("highs")
    # Query the actual native version without an optimization or reduction.
    solver <- highs::hi_new_solver(highs::hi_new_model())
    solver_version <- highs::hi_solver_version(solver)
    solver_load_ns <- duration(started)
    head <- suppressWarnings(system2("git", c("-C", shQuote(repo), "rev-parse", "HEAD"),
                                     stdout = TRUE, stderr = FALSE))
    state$runtime <- runtime
    state$version <- list(
      language = "r", runtime = list(name = "R", version = as.character(getRversion()),
                                    platform = R.version$platform),
      package = list(name = "cldreducer", version = unname(description[1L, "Version"])),
      dependencies = list(Matrix = as.character(utils::packageVersion("Matrix")),
                          highs = as.character(utils::packageVersion("highs")),
                          jsonlite = as.character(utils::packageVersion("jsonlite")),
                          microbenchmark = if (clock$description$fallback) NULL else
                            as.character(utils::packageVersion("microbenchmark"))),
      solver = list(name = "HiGHS", version = solver_version),
      module_load_ns = module_load_ns, solver_load_ns = solver_load_ns,
      load_notes = paste("Module load includes Matrix and source evaluation in a private environment.",
                         "Solver load includes highs and empty solver creation for the native version query.",
                         "No optimization runs during version."),
      source_head = if (length(head)) head[[1L]] else NULL,
      repo = repo, timer = clock$description,
      settings = list(presolve = "off", threads = 1L, parallel = "off", mip_rel_gap = 0,
                      mip_abs_gap = 0, primal_feasibility_tolerance = 1e-9,
                      mip_feasibility_tolerance = 1e-9),
      settings_kind = "declared_contract",
      settings_notes = paste("These values declare the production adapter contract; version does not validate them.",
                             "threads is the R highs control setting, not the native model threads option.",
                             "Profile metrics.solver_settings records observations before each real native run.")
    )
    invisible(NULL)
  }

  column <- function(values) unlist(lapply(values, function(value) {
    if (is.null(value)) NA else value
  }), use.names = FALSE)
  rows_to_frame <- function(rows, empty_columns) {
    if (!length(rows)) {
      frame <- rep(list(character(0)), length(empty_columns))
      names(frame) <- empty_columns
    } else {
      keys <- unique(unlist(lapply(rows, names), use.names = FALSE))
      frame <- lapply(keys, function(key) column(lapply(rows, function(row) row[[key]])))
      names(frame) <- keys
    }
    as.data.frame(frame, stringsAsFactors = FALSE, check.names = FALSE)
  }
  prepare <- function(case) {
    if (!is.list(case) || !is.list(case$input) || !is.list(case$options) ||
        !("method" %in% names(case$options))) bench_error("case requires input and options.method")
    if (!is.character(case$call) || length(case$call) != 1L ||
        !case$call %in% c("adjacency", "pairs")) bench_error("case.call must be adjacency or pairs")
    options <- case$options
    allowed <- c("method", "max_cliques", "time_limit", "group1", "group2", "significant")
    if (any(!names(options) %in% allowed)) bench_error("case contains unsupported options")
    means <- if (is.null(case$input$means)) NULL else
      rows_to_frame(case$input$means, c("group", "mean"))
    if (identical(case$call, "pairs")) {
      columns <- vapply(c("group1", "group2", "significant"), function(key) {
        if (is.null(options[[key]])) key else options[[key]]
      }, character(1))
      args <- c(list(pairs = rows_to_frame(case$input$pairs, columns), means = means), options)
      name <- "reduce_letters"
    } else {
      rows <- case$input$adjacency
      # Ragged rows remain invalid. rbind would otherwise recycle a short row.
      adjacency <- if (!length(rows) || length(unique(lengths(rows))) != 1L) rows else
        do.call(rbind, lapply(rows, column))
      groups <- case$input$groups
      if (!is.null(groups)) groups <- as.character(column(groups))[seq_along(groups)]
      args <- c(list(adjacency = adjacency, groups = groups, means = means), options)
      name <- "reduce_from_adjacency"
    }
    list(name = name, args = args)
  }
  invoke <- function(prepared) do.call(state$runtime[[prepared$name]], prepared$args)
  normalize <- function(result) {
    groups <- result$groups
    at_letters <- match(groups, names(result$letters))
    at_tokens <- match(groups, names(result$assignments))
    frame <- state$runtime$as.data.frame.cld_reduction(result)
    # Explicit lists keep singleton and empty vectors as arrays with auto_unbox.
    list(groups = unname(as.list(groups)),
         assignments = lapply(at_tokens, function(i) unname(as.list(result$assignments[[i]]))),
         letters = unname(as.list(result$letters[at_letters])),
         adjacency = lapply(seq_len(nrow(result$adjacency)), function(i) {
           unname(as.list(as.logical(result$adjacency[i, ])))
         }),
         method = result$method, relationship_preserved = result$relationship_preserved,
         stats = result$stats,
         rows = lapply(seq_len(nrow(frame)), function(i) {
           list(group = frame$group[[i]], letters = frame$letters[[i]],
                assignments = frame$assignments[[i]])
         }))
  }

  instrument <- function(prepared, action) {
    runtime <- state$runtime
    saved <- list()
    # Restore every binding and its lock status, including failures in hook setup.
    replace <- function(env, name, replacement) {
      if (!exists(name, envir = env, inherits = FALSE)) {
        stop("Unsupported runtime hook: ", name)
      }
      old <- get(name, envir = env, inherits = FALSE)
      locked <- bindingIsLocked(name, env)
      saved[[length(saved) + 1L]] <<- list(env = env, name = name, old = old, locked = locked)
      if (locked) unlockBinding(name, env)
      assign(name, replacement, envir = env)
      if (locked) lockBinding(name, env)
      invisible(old)
    }
    on.exit({
      for (item in rev(saved)) {
        if (bindingIsLocked(item$name, item$env)) unlockBinding(item$name, item$env)
        assign(item$name, item$old, envir = item$env)
        if (item$locked) lockBinding(item$name, item$env)
      }
    }, add = TRUE)
    observation <- new.env(parent = emptyenv())
    observation$canonical <- NULL
    original_canonical <- runtime$solve_canonical
    capture <- function(...) {
      solution <- original_canonical(...)
      observation$canonical <- list(selected = unname(as.list(as.integer(solution$selected))),
                                    objective = as.integer(solution$minimum))
      solution
    }
    replace(runtime, "solve_canonical", capture)
    if (identical(action, "capture")) {
      result <- invoke(prepared)
      if (is.null(observation$canonical)) stop("The public API did not call solve_canonical")
      return(list(result = normalize(result), canonical = observation$canonical))
    }

    phase_names <- c("input", "vertex_reduction", "enumeration", "model_construction",
                     "essential_scan", "adapter_setup", "model_load", "initial_optimization",
                     "canonical_trials", "output_expansion", "final_validation", "total")
    observation$phases <- stats::setNames(rep(list(NULL), length(phase_names)), phase_names)
    observation$solve_count <- 0L
    observation$solver_total_ns <- 0
    observation$probe_ns <- 0
    observation$feasible <- 0L
    observation$infeasible <- 0L
    observation$feasible_ns <- 0
    observation$infeasible_ns <- 0
    observation$counters <- list()
    observation$solver_settings <- list()
    observation$settings_errors <- list()
    observation$trial <- FALSE
    observation$required <- NULL
    observation$model <- NULL
    observation$strategy <- NULL
    observation$render_total <- NULL
    add_phase <- function(name, elapsed) {
      previous <- observation$phases[[name]]
      observation$phases[[name]] <- if (is.null(previous)) elapsed else previous + elapsed
    }
    measure_probe <- function(callback) {
      started <- now()
      on.exit({ observation$probe_ns <- observation$probe_ns + duration(started) }, add = TRUE)
      callback()
    }
    hook <- function(env, name, phase = NULL, before = NULL, after = NULL, exclude_probes = FALSE) {
      original <- get(name, envir = env, inherits = FALSE)
      wrapper <- function(...) {
        args <- list(...)
        if (!is.null(before)) before(args)
        probes_before <- observation$probe_ns
        started <- now()
        answer <- do.call(original, args)
        elapsed <- duration(started)
        if (exclude_probes) elapsed <- elapsed - (observation$probe_ns - probes_before)
        if (!is.null(phase)) add_phase(phase, elapsed)
        if (!is.null(after)) after(answer, args, elapsed)
        answer
      }
      replace(env, name, wrapper)
    }
    for (name in c("pairs_to_graph", "adjacency_to_graph")) {
      hook(runtime, name, "input", after = function(answer, args, elapsed) {
        observation$graph <- answer
      })
    }
    hook(runtime, "reduce_graph_vertices", "vertex_reduction", after = function(answer, args, elapsed) {
      observation$reduced <- answer
    })
    hook(runtime, "maximal_cliques", "enumeration", after = function(answer, args, elapsed) {
      observation$cliques <- answer
    })
    hook(runtime, "graph_context", "model_construction")
    for (name in c("build_model", "build_letter_model")) {
      hook(runtime, name, "model_construction", after = function(answer, args, elapsed) {
        observation$model <- answer
      })
    }
    for (name in c("assignment_essential_decisions", "letter_essential_decisions")) {
      hook(runtime, name, "essential_scan", after = function(answer, args, elapsed) {
        observation$required <- answer
      })
    }
    # Obtain the strategy from the same production call that validates the method.
    hook(runtime, "check_method", after = function(answer, args, elapsed) {
      observation$strategy <- answer
    })
    notes <- list(
      source_head = state$version$source_head, timer = clock$description,
      timing = paste("Profiles include hook overhead. Total includes the public API call only.",
                     "Canonical trials include adapter setup, model loading and optimization.",
                     "Solver and trial times exclude measured diagnostic probe_ns; total includes it.",
                     "Do not sum overlapping stages. Profile times are not acceptance timings."),
      probe_scope = paste("probe_ns measures added native option observations and counter record callbacks.",
                          "The production solver_info call and all production reads remain in solver time."),
      model_dimensions = "Constraints and nonzeros describe the actual initial builder model, before canonical cap rows.",
      edges = "edges counts the input graph; edges_after counts the reduced graph.",
      unavailable = stats::setNames(list(), character())
    )
    # Measure a lower bound for hook cost without running a solver or changing
    # production state. Per-hook callbacks and function-copy costs are additional.
    probe <- new.env(parent = emptyenv())
    probe$call <- function(...) NULL
    started <- now()
    for (i in seq_len(1000L)) probe$call()
    direct_probe_ns <- duration(started)
    hook(probe, "call")
    started <- now()
    for (i in seq_len(1000L)) probe$call()
    wrapped_probe_ns <- duration(started)
    notes$overhead_probe <- list(
      iterations = 1000L, direct_ns = direct_probe_ns, wrapped_ns = wrapped_probe_ns,
      note = paste("Empty function probe outside total. The difference estimates minimum wrapper overhead.",
                   "Metric callbacks and the validation function copy add costs. This estimate is not subtracted.")
    )
    if (identical(action, "preprocess")) {
      replace(runtime, "solve_canonical", function(model, time_limit, strategy) {
        observation$model <- model
        observation$required <- strategy$essential_decisions(model)
        stop(structure(list(message = "preprocessing complete", call = NULL),
                       class = c("benchmark_preprocess_done", "condition")))
      })
    } else {
      for (name in c("expand_graph_columns", "assignment_columns", "letter_columns")) {
        hook(runtime, name, "output_expansion")
      }
      # Preserve evaluation in render_result's own frame. This changes only the
      # profile copy and times the exact production validation expressions.
      render <- runtime$render_result
      expressions <- as.list(body(render))
      validation <- vapply(expressions, function(expr) {
        if (!is.call(expr)) return(FALSE)
        assignment <- identical(expr[[1L]], as.name("<-")) && identical(expr[[2L]], as.name("shared"))
        check <- identical(expr[[1L]], as.name("if")) &&
          any(c("shared", "solution") %in% all.names(expr[[2L]]))
        assignment || check
      }, logical(1))
      if (sum(validation) == 3L && requireNamespace("digest", quietly = TRUE)) {
        original_text <- paste(deparse(body(render), width.cutoff = 500L), collapse = "\n")
        render_environment <- new.env(parent = environment(render))
        render_environment$.bench_validation <- function(expr, frame) {
          started <- now()
          on.exit(add_phase("final_validation", duration(started)), add = TRUE)
          eval(expr, envir = frame)
        }
        for (i in which(validation)) {
          expressions[[i]] <- substitute(.bench_validation(quote(EXPR), environment()),
                                         list(EXPR = expressions[[i]]))
        }
        body(render) <- as.call(expressions)
        environment(render) <- render_environment
        patch <- paste(original_text, paste(deparse(body(render), width.cutoff = 500L), collapse = "\n"),
                       sep = "\n--- profile copy ---\n")
        notes$temporary_patch <- list(kind = "in memory render_result function copy",
                                     source_head = state$version$source_head,
                                     sha256 = digest::digest(patch, algo = "sha256", serialize = FALSE),
                                     hash_input = "Original body, separator, patched body from deparse(width.cutoff=500).")
        replace(runtime, "render_result", render)
      } else {
        notes$unavailable$final_validation <- paste("render_result validation expressions changed, or digest is unavailable.",
                                                   "Output expansion includes final validation.")
      }
      hook(runtime, "render_result", after = function(answer, args, elapsed) {
        observation$render_total <- elapsed
        validation_ns <- observation$phases$final_validation
        add_phase("output_expansion", elapsed - if (is.null(validation_ns)) 0 else validation_ns)
      })
      hook(runtime, "solve_lp", exclude_probes = TRUE, before = function(args) {
        observation$solve_count <- observation$solve_count + 1L
        # Production passes sum_limit as the fourth positional argument.
        cap <- if ("sum_limit" %in% names(args)) args$sum_limit else
          if (length(args) >= 4L) args[[4L]] else NULL
        observation$trial <- !is.null(cap)
      }, after = function(answer, args, elapsed) {
        observation$solver_total_ns <- observation$solver_total_ns + elapsed
        if (observation$trial) {
          if (identical(answer$status, "optimal")) {
            observation$feasible <- observation$feasible + 1L
            observation$feasible_ns <- observation$feasible_ns + elapsed
          } else if (identical(answer$status, "infeasible")) {
            observation$infeasible <- observation$infeasible + 1L
            observation$infeasible_ns <- observation$infeasible_ns + elapsed
          }
          add_phase("canonical_trials", elapsed)
        }
      })
      highs <- asNamespace("highs")
      for (name in c("highs_model", "highs_control", "set_number_of_threads", "hi_solver_set_options")) {
        if (exists(name, highs, inherits = FALSE)) hook(highs, name, "adapter_setup")
      }
      if (exists("new_solver", highs, inherits = FALSE)) {
        hook(highs, "new_solver", "model_load")
        notes$model_load <- "Native new_solver call includes both solver creation and model loading; the native API does not split them."
      } else notes$unavailable$model_load <- "The highs namespace has no new_solver wrapper."
      if (exists("solver_run", highs, inherits = FALSE)) {
        hook(highs, "solver_run", before = function(args) {
          # Read actual options after production setup and before native execution.
          # highs 1.14.0.2 misindexes hi_solver_get_options(keys=...). Reading all
          # options also queries unsupported entries. Use the typed getters.
          measure_probe(function() tryCatch({
            solver <- args[[1L]]
            values <- list()
            for (key in c("presolve", "parallel", "solver")) {
              values[[key]] <- highs::hi_solver_get_str_option(solver, key)
            }
            for (key in c("threads", "random_seed")) {
              values[[key]] <- highs::hi_solver_get_int_option(solver, key)
            }
            for (key in c("mip_rel_gap", "mip_abs_gap", "primal_feasibility_tolerance",
                          "dual_feasibility_tolerance", "mip_feasibility_tolerance")) {
              values[[key]] <- highs::hi_solver_get_dbl_option(solver, key)
            }
            values$r_global_threads <- get("get_number_of_threads", highs)()
            if (any(vapply(values, function(value) length(value) != 1L || is.na(value), logical(1)))) {
              stop("An observed solver setting is missing")
            }
            time_limit <- highs::hi_solver_get_dbl_option(solver, "time_limit")
            observation$solver_settings[[length(observation$solver_settings) + 1L]] <- list(
              solve = observation$solve_count, values = values,
              excluded_values = list(time_limit = if (is.infinite(time_limit)) "Inf" else time_limit))
          }, error = function(error) {
            observation$settings_errors[[length(observation$settings_errors) + 1L]] <- list(
              solve = observation$solve_count, message = conditionMessage(error))
          }))
        }, after = function(answer, args, elapsed) {
          if (!observation$trial) add_phase("initial_optimization", elapsed)
        })
      } else notes$unavailable$initial_optimization <- "The highs namespace has no solver_run wrapper."
      if (exists("solver_info", highs, inherits = FALSE)) {
        hook(highs, "solver_info", after = function(answer, args, elapsed) {
          measure_probe(function() {
            observation$counters[[length(observation$counters) + 1L]] <- list(
              solve = observation$solve_count, canonical_trial = observation$trial, info = answer)
          })
        })
      }
    }

    started <- now()
    result <- tryCatch(invoke(prepared), benchmark_preprocess_done = function(e) NULL)
    observation$phases$total <- duration(started)
    model <- observation$model
    if (is.null(model) || is.null(observation$required)) stop("Production model or essential scan was not observed")
    problem <- model$problem
    essential <- problem$decision_columns %in% observation$required
    canonical <- observation$canonical
    counters <- if (length(observation$counters)) {
      list(available = TRUE, source = "highs native solver_info", by_solve = observation$counters)
    } else list(available = FALSE, reason = if (identical(action, "preprocess"))
      "Preprocessing does not run the solver." else "No highs solver_info call was observed.")
    settings <- list(
      available = observation$solve_count > 0L && !length(observation$settings_errors) &&
        identical(vapply(observation$solver_settings, function(record) record$solve, integer(1)),
                  seq_len(observation$solve_count)),
      records = observation$solver_settings,
      source = paste("HiGHS typed native option getters immediately before solver_run.",
                     "r_global_threads comes from highs namespace get_number_of_threads()."),
      excluded_from_stable_comparison = list("time_limit"),
      notes = paste("values.threads is the native model option; 0 means native automatic selection.",
                    "values.r_global_threads is the R package global thread setting used by its scheduler wrapper.",
                    "It is not a native worker count. Neither value substitutes for the other.",
                    "excluded_values.time_limit is the changing per-solve budget in seconds; Inf denotes no limit.")
    )
    if (!settings$available) {
      settings$reason <- if (!observation$solve_count) "No native solver run was observed." else
        "The native option observations do not cover every solve."
      settings$errors <- observation$settings_errors
    }
    metrics <- list(
      vertices_before = length(observation$graph$groups),
      vertices_after = nrow(observation$reduced$adjacency),
      edges = sum(observation$graph$adjacency & upper.tri(observation$graph$adjacency)),
      edges_after = nrow(model$edges), maximal_cliques = length(observation$cliques),
      decision_variables = length(problem$decision_columns),
      auxiliary_variables = problem$num_cols - length(problem$decision_columns),
      constraints = nrow(problem$matrix), nonzeros = Matrix::nnzero(problem$matrix),
      essential_decisions = length(observation$required), solve_count = observation$solve_count,
      solver_total_ns = observation$solver_total_ns,
      probe_ns = observation$probe_ns,
      canonical_feasible_trials = observation$feasible,
      canonical_infeasible_trials = observation$infeasible,
      canonical_feasible_trials_ns = observation$feasible_ns,
      canonical_infeasible_trials_ns = observation$infeasible_ns,
      final_zero_decisions = if (is.null(canonical)) NULL else sum(unlist(canonical$selected) == 0L),
      essential_cover = observation$strategy$coverage(model, essential),
      selected = if (is.null(canonical)) NULL else canonical$selected,
      objective = if (is.null(canonical)) NULL else canonical$objective,
      solver_counters = counters, solver_settings = settings
    )
    if (identical(action, "preprocess")) {
      for (name in c("adapter_setup", "model_load", "initial_optimization", "canonical_trials",
                     "output_expansion", "final_validation")) {
        notes$unavailable[[name]] <- "Preprocessing stops after the production essential scan."
      }
      notes$unavailable$selected <- "Preprocessing does not produce a canonical solution."
      notes$unavailable$objective <- "Preprocessing does not optimize the objective."
      notes$unavailable$final_zero_decisions <- "Preprocessing does not produce a canonical solution."
    } else {
      if (is.null(canonical)) stop("The public API did not return a canonical decision vector")
      # No trial is an observed fact, unlike an unavailable timer split.
      if (metrics$canonical_feasible_trials + metrics$canonical_infeasible_trials == 0L) {
        observation$phases$canonical_trials <- 0
      }
    }
    for (name in phase_names) {
      if (is.null(observation$phases[[name]]) && is.null(notes$unavailable[[name]])) {
        notes$unavailable[[name]] <- "No call at the configured production hook was observed."
      }
    }
    notes$render_result_total_ns <- observation$render_total
    notes$solver_counters <- paste("Native info values are returned without reinterpretation.",
                                    "Negative counters are native unavailable markers; nonfinite values serialize as null.")
    answer <- list(metrics = metrics, phases_ns = observation$phases, profile_notes = notes)
    if (!is.null(result)) answer <- c(list(result = normalize(result), canonical = canonical), answer)
    answer
  }

  dispatch <- function(request) {
    if (!is.list(request) || is.null(names(request)) || !is.character(request$action) ||
        length(request$action) != 1L) bench_error("request requires one action string")
    action <- request$action
    if (!action %in% c("version", "measure", "capture", "profile", "preprocess")) {
      bench_error("unsupported action")
    }
    load_runtime()
    if (identical(action, "version")) return(c(list(ok = TRUE, action = action), state$version))
    prepared <- prepare(request$case)
    if (identical(action, "measure")) {
      iterations <- request$iterations
      if (!is.numeric(iterations) || length(iterations) != 1L || !is.finite(iterations) ||
          iterations < 1 || iterations != floor(iterations) || iterations > .Machine$integer.max) {
        bench_error("iterations must be a positive integer at most 2147483647")
      }
      # Resolve the public function and native arguments before the timed region.
      fun <- state$runtime[[prepared$name]]
      args <- prepared$args
      started <- now()
      for (i in seq_len(iterations)) result <- do.call(fun, args)
      elapsed_ns <- duration(started)
      answer <- list(elapsed_ns = elapsed_ns, iterations = iterations, result = normalize(result))
    } else {
      if (identical(action, "profile")) {
        # No hooks are installed yet. The harness warms this same profile path
        # before collecting observations. Keep the reference call outside total.
        started <- now()
        reference <- invoke(prepared)
        reference_ns <- duration(started)
      }
      answer <- instrument(prepared, action)
      if (identical(action, "profile")) {
        if (!identical(normalize(reference), answer$result)) {
          stop("Profile and uninstrumented overhead reference returned different results")
        }
        answer$profile_notes$full_call_overhead <- list(
          reference_ns = reference_ns,
          instrumented_ns = answer$phases_ns$total,
          instrumented_minus_reference_ns = answer$phases_ns$total - reference_ns,
          ratio = if (reference_ns > 0) answer$phases_ns$total / reference_ns else NULL,
          uninstrumented_calls = 1L,
          note = paste("One uninstrumented full API reference call precedes hook setup, outside profile total.",
                       "The harness warms this same profile path before collection; one standalone request can be cold.",
                       "Both calls exclude request conversion and result normalization.",
                       "The signed difference includes order, cache, GC and timer noise; it can be negative.",
                       "This is a diagnostic observation, not an overhead correction or acceptance timing.")
        )
      }
    }
    c(list(ok = TRUE, action = action), answer)
  }
  handle <- function(request) {
    action <- if (is.list(request) && is.character(request$action) && length(request$action) == 1L)
      request$action else NULL
    tryCatch(dispatch(request), error = function(error) {
      list(ok = FALSE, action = action,
           error = list(kind = class(error)[[1L]], message = conditionMessage(error)))
    })
  }
  list(handle = handle, state = state)
}

bench_main <- function(args = commandArgs(trailingOnly = TRUE)) {
  repo <- NULL
  presolve <- "off"
  i <- 1L
  while (i <= length(args)) {
    if (!args[[i]] %in% c("--repo", "--presolve") || i == length(args)) {
      bench_error("Usage: Rscript r_driver.R --repo ABSOLUTE_PATH [--presolve off]")
    }
    if (args[[i]] == "--repo") repo <- args[[i + 1L]] else presolve <- args[[i + 1L]]
    i <- i + 2L
  }
  if (is.null(repo)) bench_error("--repo is required")
  driver <- bench_driver(repo, presolve)
  input <- file("stdin", open = "r", encoding = "UTF-8")
  on.exit(close(input), add = TRUE)
  repeat {
    line <- readLines(input, n = 1L, warn = FALSE)
    if (!length(line)) break
    response <- tryCatch(driver$handle(jsonlite::fromJSON(line, simplifyVector = FALSE)),
                         error = function(error) list(ok = FALSE, action = NULL,
                           error = list(kind = "benchmark_invalid_request", message = conditionMessage(error))))
    # jsonlite's digits=NA uses only 15 significant digits. Preserve doubles.
    cat(jsonlite::toJSON(response, auto_unbox = TRUE, null = "null", na = "null", digits = 17), "\n", sep = "")
    flush(stdout())
  }
  invisible(NULL)
}

if (sys.nframe() == 0L) {
  tryCatch(bench_main(), error = function(error) {
    message(conditionMessage(error))
    quit(status = 1L)
  })
}
