"""
Tests for language-specific euphony transformations in word list joining.

Covers Italian and Spanish euphony rules loaded from JSON config files.
"""
import unittest

from ovos_workshop.skills.util import join_word_list


class TestJoinWordListIt(unittest.TestCase):

    def test_basic_conjunction_and(self):
        result = join_word_list(["mare", "montagna"], "and", ",", "it-IT")
        self.assertEqual(result, "mare e montagna")

    def test_basic_conjunction_or(self):
        result = join_word_list(["mare", "montagna"], "or", ",", "it-IT")
        self.assertEqual(result, "mare o montagna")

    def test_euphonic_conjunction_or(self):
        result = join_word_list(["mare", "oceano"], "or", ",", "it-IT")
        self.assertEqual(result, "mare od oceano")

    def test_euphonic_conjunction_and(self):
        result = join_word_list(["inverno", "estate"], "and", ",", "it-IT")
        self.assertEqual(result, "inverno ed estate")

    def test_euphonic_conjunction_or_with_other_words(self):
        result = join_word_list(["libro", "orologio"], "or", ",", "it-IT")
        self.assertEqual(result, "libro od orologio")

    def test_join_three_words(self):
        result = join_word_list(["mare", "estate", "inverno"], "and", ",", "it-IT")
        self.assertEqual(result, "mare, estate e inverno")

    def test_empty_list(self):
        result = join_word_list([], "and", ",", "it-IT")
        self.assertEqual(result, "")

    def test_single_word(self):
        result = join_word_list(["mare"], "and", ",", "it-IT")
        self.assertEqual(result, "mare")

    def test_multiple_euphonic_transformations(self):
        result = join_word_list(["casa", "estate", "inverno", "autunno"], "and", ",", "it-IT")
        self.assertEqual(result, "casa, estate, inverno e autunno")

    def test_mixed_conjunctions(self):
        result = join_word_list(["mare", "oceano", "isola"], "or", ",", "it-IT")
        self.assertEqual(result, "mare, oceano o isola")


class TestJoinWordListEs(unittest.TestCase):

    def test_euphonic_conjunction_and(self):
        self.assertEqual(
            join_word_list(["Juan", "Irene"], "and", ",", "es-ES"),
            "Juan e Irene")
        self.assertEqual(
            join_word_list(["vaqueros", "indios"], "and", ",", "es-ES"),
            "vaqueros e indios")
        self.assertEqual(
            join_word_list(["Manuel", "Hilario"], "and", ",", "es-ES"),
            "Manuel e Hilario")
        self.assertEqual(
            join_word_list(["mujer", "hijos"], "and", ",", "es-ES"),
            "mujer e hijos")
        self.assertEqual(
            join_word_list(["mató", "hirió"], "and", ",", "es-ES"),
            "mató e hirió")
        self.assertEqual(
            join_word_list(["geografía", "historia"], "and", ",", "es-ES"),
            "geografía e historia")

    def test_euphonic_conjunction_exceptions_and(self):
        # When following word starts by (H)IA, (H)IE or (H)IO, then usual Y is used
        self.assertEqual(
            join_word_list(["frio", "hielo"], "and", ",", "es-ES"),
            "frio y hielo")
        self.assertEqual(
            join_word_list(["cloro", "iodo"], "and", ",", "es-ES"),
            "cloro y iodo")
        self.assertEqual(
            join_word_list(["Eta", "Iota"], "and", ",", "es-ES"),
            "Eta y Iota")
        self.assertEqual(
            join_word_list(["paz", "hiógrafo"], "and", ",", "es-ES"),
            "paz y hiógrafo")

    def test_euphonic_conjunction_or(self):
        self.assertEqual(
            join_word_list(["Manuel", "Óscar"], "or", ",", "es-ES"),
            "Manuel u Óscar")
        self.assertEqual(
            join_word_list(["unos", "otros"], "or", ",", "es-ES"),
            "unos u otros")


if __name__ == "__main__":
    unittest.main()
