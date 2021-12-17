# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

from .base import Prediction
from spliced.logger import logger
import spliced.utils as utils
import itertools

import os
import re


def add_to_path(path):
    path = "%s:%s" % (path, os.environ["PATH"])
    os.putenv("PATH", path)
    os.environ["PATH"] = path


class LibabigailPrediction(Prediction):

    abicompat = None

    def find_abicompat(self):
        """
        Find abicompat and add to class
        """
        abicompat = utils.which("abicompat")
        if not abicompat["message"]:
            logger.warning("abicompat not found on path, will look for spack instead.")

            # Try getting from spack
            try:
                utils.add_spack_to_path()
                import spack.store

                installed_specs = spack.store.db.query("libabigail")
                if not installed_specs:
                    import spack.spec

                    abi = spack.spec.Spec("libabigail")
                    abi.concretize()
                    abi.package.do_install(force=True)
                else:
                    abi = installed_specs[0]

                add_to_path(os.path.join(abi.prefix, "bin"))
                abicompat = utils.which("abicompat")

            except:
                logger.error(
                    "You must either have abicompat (libabigail) on the path, or spack."
                )
                return

        if not abicompat["message"]:
            logger.error(
                "You must either have abicompat (libabigail) on the path, or spack."
            )
            return

        # This is the executable path
        self.abicompat = abicompat["message"]

    def predict(self, splice):
        """
        Run libabigail to add to the predictions
        """
        # If no splice libs, cut out early
        if not splice.libs:
            return

        if not self.abicompat:
            self.find_abicompat()

        # We have TWO cases here:
        # Case 1: We ONLY have a list of libs that were spliced.
        if (
            "spliced" in splice.libs
            and "original" in splice.libs
            and splice.libs["spliced"]
        ):
            self.splice_equivalent_libs(splice, splice.libs["spliced"])

        # Case 2: We are mocking a splice, and we have TWO sets of libs: some original, and some to replace with
        elif "dep" in splice.libs and "replace" in splice.libs:
            self.splice_different_libs(
                splice, splice.libs["dep"], splice.libs["replace"]
            )

    def splice_different_libs(self, splice, original_libs, replace_libs):
        """
        In the case of splicing "the same lib" into itself (a different version)
        we can do matching based on names.
        """
        # If we have spliced binaries, this means the spack splice was successful.
        # Otherwise, we do not, but we have the original deps to test
        binaries = splice.get_binaries()

        # Flatten original and replacement libs
        original_libs = list(itertools.chain(*[x["paths"] for x in original_libs]))
        replace_libs = list(itertools.chain(*[x["paths"] for x in replace_libs]))

        # Assemble a set of predictions
        predictions = []
        for binary in binaries:
            for original_lib in original_libs:
                for replace_lib in replace_libs:

                    # Run abicompat to make a prediction
                    command = "%s %s %s %s" % (
                        self.abicompat,
                        binary,
                        original_lib,
                        replace_lib,
                    )
                    res = utils.run_command(command)

                    # Additional debugging
                    print(command)
                    print(res)
                    print()
                    res["binary"] = binary
                    res["splice_type"] = "different_lib"

                    # The spliced lib and original
                    res["replace"] = replace_lib
                    res["lib"] = original_lib

                    # If there is a libabigail output, print to see
                    if res["message"] != "":
                        print(res["message"])
                    res["prediction"] = res["message"] == "" and res["return_code"] == 0
                    predictions.append(res)

        if predictions:
            splice.predictions["libabigail"] = predictions

    def splice_equivalent_libs(self, splice, libs):
        """
        In the case of splicing "the same lib" into itself (a different version)
        we can do matching based on names.
        """
        # Flatten original libs into flat list
        original_libs = list(
            itertools.chain(*[x["paths"] for x in splice.libs.get("original", [])])
        )

        # If we have spliced binaries, this means the spack splice was successful.
        # Otherwise, we do not, but we have the original deps to test
        binaries = splice.get_binaries()

        # Assemble a set of predictions
        predictions = []
        for binary in binaries:
            for libset in libs:
                for lib in libset["paths"]:

                    # Try to match libraries based on prefix (versioning is likely to change)
                    libprefix = os.path.basename(lib).split(".")[0]

                    # Find an original library path with the same prefix
                    originals = [
                        x
                        for x in original_libs
                        if os.path.basename(x).startswith(libprefix)
                    ]
                    if not originals:
                        logger.warning(
                            "Warning, original comparison library not found for %s, required for abicompat."
                            % lib
                        )
                        continue

                    # The best we can do is compare all contender matches
                    for original in originals:

                        # Run abicompat to make a prediction
                        res = utils.run_command(
                            "%s %s %s %s" % (self.abicompat, binary, original, lib)
                        )
                        res["binary"] = binary
                        res["splice_type"] = "same_lib"

                        # The spliced lib and original
                        res["lib"] = lib
                        res["original_lib"] = lib

                        # If there is a libabigail output, print to see
                        if res["message"] != "":
                            print(res["message"])
                        res["prediction"] = (
                            res["message"] == "" and res["return_code"] == 0
                        )
                        predictions.append(res)

        if predictions:
            splice.predictions["libabigail"] = predictions
            print(splice.predictions)
