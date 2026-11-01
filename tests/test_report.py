"""Checks of the report source, of its data markers and of the generated PDF."""
import csv
import os
import re
import statistics
import sys
import unittest

from pypdf import PdfReader

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT_DIR = os.path.join(ROOT, "docs", "report")
RESULTS = os.path.join(ROOT, "experiments", "results")
SOURCE = os.path.join(REPORT_DIR, "informe.md")
PDF = os.path.join(REPORT_DIR, "informe.pdf")
sys.path.insert(0, REPORT_DIR)

import build_report  # noqa: E402

REPO = "https://github.com/EstebanBautista/MP3"

# The required section titles, plus what the rubric needs to find quickly.
REQUIRED_TITLES = [
    "Descripción del problema",
    "Reglas de la simulación",
    "Diseño 1: secuencial",
    "Diseño 2: estático con Pthreads",
    "Diseño 3: adaptativo con OpenMP",
    "Ventajas y desventajas de cada diseño",
    "Preguntas por diseño",
    "Comparación: rendimiento, complejidad de desarrollo y mantenimiento",
    "Verificación de la corrección",
    "Resultados de rendimiento",
    "Experimentos del ecosistema",
    "Interfaz visual",
    "Cómo ejecutar el programa",
    "Conclusión",
    "Mapa de la rúbrica y del enunciado",
]


def source_text():
    with open(SOURCE, encoding="utf-8") as f:
        return f.read()


def pdf_pages():
    return PdfReader(PDF).pages


def pdf_text():
    return "\n".join(page.extract_text() for page in pdf_pages())


def squeeze(text):
    return re.sub(r"\s+", "", text)


def medians(path):
    """(design, mode, case, threads) -> median wall time, computed apart from the builder."""
    groups = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            key = (row["design"], row["mode"], row["case"], row["threads"])
            groups.setdefault(key, []).append(float(row["wall"]))
    return {key: statistics.median(values) for key, values in groups.items()}


class TestSource(unittest.TestCase):
    def test_all_sections_present(self):
        headings = re.findall(r"^#{1,3} (.+?)(?: \{#.+\})?$", source_text(), re.M)
        for title in REQUIRED_TITLES:
            self.assertTrue(any(h == title for h in headings), title)

    def test_figures_exist(self):
        names = re.findall(r"^!\[.*?\]\((.+?)\)$", source_text(), re.M)
        self.assertGreaterEqual(len(names), 12)
        for name in names:
            self.assertTrue(os.path.isfile(os.path.join(REPORT_DIR, name)), name)

    def test_all_measured_figures_are_used(self):
        text = source_text()
        for name in ("perf_aceleracion", "perf_eficiencia", "perf_tiempo_cpu", "perf_desequilibrio",
                     "perf_barreras", "perf_aceleracion_linux", "eco_base_serie", "eco_transitorio",
                     "eco_series_rocas", "eco_series_parametros", "eco_estabilidad"):
            self.assertIn(name + ".png", text)

    def test_key_numbers_match_csv(self):
        """Every wall time marker resolves to the median in the CSV, in the report's own format."""
        win = medians(os.path.join(RESULTS, "performance.csv"))
        linux = medians(os.path.join(RESULTS, "performance_linux.csv"))
        design = {"seq": ("seq", "-"), "pth": ("pth", "-"),
                  "omp_a": ("omp", "adaptive"), "omp_s": ("omp", "static")}
        markers = re.findall(r"\{\{perf:(win|linux):([^:]+):(\w+):(\d+):wall\}\}", source_text())
        self.assertGreater(len(markers), 20)
        for platform, case, name, threads in markers:
            table = win if platform == "win" else linux
            expected = table[(*design[name], case, threads)]
            marker = "{{perf:%s:%s:%s:%s:wall}}" % (platform, case, name, threads)
            self.assertEqual(build_report.resolve_markers(marker), ("%.3f" % expected).replace(".", ","))

    def test_no_unresolved_markers(self):
        resolved = build_report.resolve_markers(source_text())
        unresolved = [m for m in re.findall(r"\{\{(.+?)\}\}", resolved)
                      if not m.startswith(build_report.LAYOUT_MARKERS)]
        self.assertEqual(unresolved, [])

    def test_no_loose_measurements(self):
        """Times and speedups in the prose must come from a marker, not be typed by hand."""
        typed = []
        for line in source_text().splitlines():
            without = re.sub(r"\{\{.+?\}\}", "", line)
            typed += re.findall(r"\b\d+,\d+ ?(?:s\b|µs|%)|[x×]\d+,\d+", without)
        self.assertEqual(typed, [])

    def test_values_match_committed_summary(self):
        """The builder's medians, IQR, speedup and efficiency equal the tables of the results summary."""
        with open(os.path.join(RESULTS, "performance_summary.md"), encoding="utf-8") as f:
            text = f.read()
        names = {"Pthreads": "pth", "OpenMP adaptativo": "omp_a", "OpenMP estatico": "omp_s"}
        win, linux = text.split("## Tablas completas (Linux")
        checked = 0
        for platform, part in (("win", win), ("linux", linux)):
            for section in re.split(r"^### ", part, flags=re.M)[1:]:
                case = section.split()[0]
                for name, cells in re.findall(r"^\| (Pthreads|OpenMP \w+) \|(.+?)\| \+[\d.]+ % \|$", section, re.M):
                    for threads, cell in zip((1, 2, 4, 8, 16), cells.split("|")):
                        match = re.match(r" ([\d.]+) \[([\d.]+)\] x([\d.]+) e([\d.]+) ", cell)
                        for metric, value in zip(("wall", "iqr", "speedup", "eff"), match.groups()):
                            marker = "{{perf:%s:%s:%s:%d:%s}}" % (platform, case, names[name], threads, metric)
                            self.assertEqual(build_report.resolve_markers(marker), value.replace(".", ","), marker)
                            checked += 1
        self.assertEqual(checked, 480)

    def test_unknown_marker_is_an_error(self):
        with self.assertRaises(KeyError):
            build_report.resolve_markers("{{perf:win:nope:pth:8:wall}}")
        with self.assertRaises(ValueError):
            build_report.resolve_markers("{{nothing:at:all}}")

    def test_values_from_text_files(self):
        self.assertEqual(build_report.resolve_markers("{{tsan:omp:total}}"), self._tsan_total("tsan_omp.txt"))
        self.assertEqual(build_report.resolve_markers("{{tsan:pth:total}}"), "0")
        self.assertEqual(build_report.resolve_markers("{{tsan:archer:total}}"), "0")

    @staticmethod
    def _tsan_total(name):
        with open(os.path.join(RESULTS, name), encoding="utf-8") as f:
            return re.search(r"^overall: (\d+) TSan warnings", f.read(), re.M).group(1)

    def test_rubric_table_totals_100(self):
        table = source_text().split(":::table rubrica")[1].split(":::table enunciado")[0]
        points = [int(n) for n in re.findall(r"^\| .*?\((\d+)\) \|", table, re.M)]
        self.assertEqual(sum(points), 100)

    def test_adaptive_exceptions_are_stated(self):
        """Exactly the configurations where adaptive does not lower imbalance are the ones named."""
        worse = [(c, t) for c in build_report.WIN_CASES for t in (2, 4, 8, 16)
                 if build_report.perf_metric("win", c, "omp_a", t, "imb")
                 >= build_report.perf_metric("win", c, "omp_s", t, "imb")]
        self.assertEqual(worse, [("20x20", 2), ("20x20", 4)])
        self.assertIn("22 de las 24", source_text())

    def test_only_the_large_world_passes_four_times_in_every_parallel_engine(self):
        """The claim of the summary and of the main results, against the medians of the CSV."""
        win = medians(os.path.join(RESULTS, "performance.csv"))
        engines = (("pth", "-"), ("omp", "adaptive"), ("omp", "static"))

        def speedups(case, threads):
            return [win[("seq", "-", case, "1")] / win[(*e, case, threads)] for e in engines]

        passing = [case for case in build_report.WIN_CASES
                   if any(min(speedups(case, t)) > 4 for t in ("2", "4", "8", "16"))]
        self.assertEqual(passing, ["large1000x1000"])
        self.assertGreater(min(speedups("large1000x1000", "16")), 4)
        self.assertLess(min(speedups("large1000x1000", "8")), 4)
        self.assertEqual(source_text().count("es el único mundo donde Pthreads y OpenMP, adaptativo y estático, pasan de 4 veces"), 2)
        self.assertNotIn("aceleración clara en todos", source_text())

    def test_required_honesty_statements(self):
        text = source_text()
        for phrase in ("no se observaron carreras", "Archer", "libgomp", "no se investigó",
                       "no demuestra", "`staticBands`", "punto ciego", "decisión de diseño"):
            self.assertIn(phrase, text)

    def test_code_references_exist(self):
        """Functions, classes and files named in the report must exist in the sources."""
        code = ""
        for folder in ("engine", "web", "tools", "experiments", "scripts", "tests"):
            for base, _dirs, files in os.walk(os.path.join(ROOT, folder)):
                if "results" in base or "data" in base:
                    continue
                for name in files:
                    if name.endswith((".hpp", ".cpp", ".py", ".js", ".html", ".sh", ".ps1")):
                        with open(os.path.join(base, name), encoding="utf-8", errors="replace") as f:
                            code += f.read()
        for token in re.findall(r"`([^`\n]+)`", source_text()):
            function = re.fullmatch(r"(?:\w+::)?(\w+)(?:<\w+>)?\(\)", token)
            if function:
                self.assertRegex(code, r"\b%s\b" % function.group(1), token)
            elif re.fullmatch(r"(engine|web|tools|experiments|scripts|tests|docs)/[\w./-]+", token):
                self.assertTrue(os.path.exists(os.path.join(ROOT, token)), token)
            elif re.fullmatch(r"[A-Z]\w*[a-z]\w*", token):
                self.assertRegex(code, r"\b%s\b" % token, token)

    def test_engine_does_not_use_vector_or_string(self):
        """The report says the engine uses arrays and char pointers, as the course recommends."""
        folder = os.path.join(ROOT, "engine")
        for name in os.listdir(folder):
            with open(os.path.join(folder, name), encoding="utf-8") as f:
                self.assertIsNone(re.search(r"std::(vector|string)\b", f.read()), name)


class TestPdf(unittest.TestCase):
    def test_pdf_exists_and_has_reasonable_length(self):
        self.assertTrue(os.path.isfile(PDF))
        self.assertGreaterEqual(len(pdf_pages()), 15)
        self.assertLessEqual(len(pdf_pages()), 45)

    def test_no_markers_in_pdf(self):
        text = pdf_text()
        self.assertNotIn("{{", text)
        self.assertNotIn("}}", text)

    def test_placeholders_stay_visible_until_filled(self):
        text = squeeze(pdf_text())
        for mark in (build_report.TEAM + [build_report.VIDEO_URL]):
            self.assertIn(squeeze(mark), text)

    def test_accents_survive(self):
        text = pdf_text()
        for word in ("Conclusión", "Diseño", "población", "µs"):
            self.assertIn(word, text)

    def test_section_titles_in_pdf(self):
        text = squeeze(pdf_text())
        for title in REQUIRED_TITLES:
            self.assertIn(squeeze(title), text, title)

    def test_key_number_in_pdf(self):
        win = medians(os.path.join(RESULTS, "performance.csv"))
        value = ("%.3f" % win[("pth", "-", "200x200", "8")]).replace(".", ",")
        self.assertIn(value, pdf_text())

    def test_links(self):
        uris = set()
        internal = 0
        for page in pdf_pages():
            for ref in page.get("/Annots") or []:
                annotation = ref.get_object()
                action = annotation.get("/A")
                if action is not None and "/URI" in action:
                    uris.add(action["/URI"])
                elif "/Dest" in annotation or (action is not None and "/D" in action):
                    internal += 1
        for branch in ("diseno-1-secuencial", "diseno-2-estatico", "diseno-3-adaptativo"):
            self.assertIn("%s/tree/%s" % (REPO, branch), uris)
        self.assertIn(REPO, uris)
        self.assertGreater(internal, 15)

    def test_page_numbers_printed(self):
        pages = pdf_pages()
        for number in (3, len(pages)):
            self.assertRegex(pages[number - 1].extract_text(), r"(?m)\b%d\b" % number)


if __name__ == "__main__":
    unittest.main()
