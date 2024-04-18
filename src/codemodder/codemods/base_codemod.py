from __future__ import annotations

import functools
import importlib.resources
from abc import ABCMeta, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from functools import cached_property
from importlib.abc import Traversable
from pathlib import Path

from codemodder.code_directory import file_line_patterns
from codemodder.codemods.base_detector import BaseDetector
from codemodder.codemods.base_transformer import BaseTransformerPipeline
from codemodder.codetf import DetectionTool, Reference, Rule
from codemodder.context import CodemodExecutionContext
from codemodder.file_context import FileContext
from codemodder.logging import logger
from codemodder.result import ResultSet


class ReviewGuidance(Enum):
    MERGE_AFTER_REVIEW = 1
    MERGE_AFTER_CURSORY_REVIEW = 2
    MERGE_WITHOUT_REVIEW = 3


@dataclass
class Metadata:
    name: str
    summary: str
    review_guidance: ReviewGuidance
    references: list[Reference] = field(default_factory=list)
    description: str | None = None
    tool: ToolMetadata | None = None
    language: str = "python"


@dataclass
class ToolMetadata:
    name: str
    rule_id: str
    rule_name: str
    rule_url: str | None = None


class BaseCodemod(metaclass=ABCMeta):
    """
    Base class for all codemods

    Conceptually a codemod is composed of the following attributes:
    * Metadata: contains information about the codemod including its name, summary, and review guidance
    * Detector (optional): the source of results indicating which code locations the codemod should be applied
    * Transformer: a transformer pipeline that will be applied to each applicable file and perform the actual modifications

    A detector may parse result files generated by other tools or it may
    perform its own analysis at runtime, potentially by calling another tool
    (e.g. Semgrep).

    Some codemods may not require a detector if the transformation pipeline
    itself is capable of determining locations to modify.

    Codemods that apply the same transformation but use different detectors
    should be implemented as distinct codemod classes.
    """

    _metadata: Metadata
    detector: BaseDetector | None
    transformer: BaseTransformerPipeline
    default_extensions: list[str] | None

    def __init__(
        self,
        *,
        metadata: Metadata,
        detector: BaseDetector | None = None,
        transformer: BaseTransformerPipeline,
        default_extensions: list[str] | None = None,
    ):
        # Metadata should only be accessed via properties
        self._metadata = metadata
        self.detector = detector
        self.transformer = transformer
        self.default_extensions = default_extensions or [".py"]

    @property
    @abstractmethod
    def origin(self) -> str: ...

    @property
    @abstractmethod
    def docs_module_path(self) -> str: ...

    @property
    def name(self) -> str:
        return self._metadata.name

    @property
    def language(self) -> str:
        return self._metadata.language

    @property
    def id(self) -> str:
        return f"{self.origin}:{self.language}/{self.name}"

    @property
    def summary(self):
        return self._metadata.summary

    @property
    def detection_tool(self) -> DetectionTool | None:
        if self._metadata.tool is None:
            return None

        return DetectionTool(
            name=self._metadata.tool.name,
            rule=Rule(
                id=self._metadata.tool.rule_id,
                name=self._metadata.tool.rule_name,
                url=self._metadata.tool.rule_url,
            ),
        )

    @cached_property
    def docs_module(self) -> Traversable:
        return importlib.resources.files(self.docs_module_path)

    @cached_property
    def description(self) -> str:
        if self._metadata.description is None:
            doc_path = self.docs_module / f"{self.origin}_python_{self.name}.md"
            return doc_path.read_text()
        return self._metadata.description

    @property
    def review_guidance(self):
        return self._metadata.review_guidance.name.replace("_", " ").title()

    @property
    def references(self) -> list[Reference]:
        return self._metadata.references

    def describe(self):
        return {
            "codemod": self.id,
            "summary": self.summary,
            "description": self.description,
            "references": [ref.model_dump() for ref in self.references],
        }

    def _apply(
        self,
        context: CodemodExecutionContext,
        files_to_analyze: list[Path],
        rules: list[str],
    ) -> None:
        results = (
            # It seems like semgrep doesn't like our fully-specified id format
            self.detector.apply(self.name, context, files_to_analyze)
            if self.detector
            else None
        )

        files_to_analyze = (
            [
                path
                for path in files_to_analyze
                if path.suffix in self.default_extensions
            ]
            if self.default_extensions
            else files_to_analyze
        )

        process_file = functools.partial(
            self._process_file, context=context, results=results, rules=rules
        )

        with ThreadPoolExecutor() as executor:
            logger.debug("using executor with %s workers", context.max_workers)
            contexts = executor.map(process_file, files_to_analyze)
            executor.shutdown(wait=True)

        context.process_results(self.id, contexts)

    def apply(
        self,
        context: CodemodExecutionContext,
        files_to_analyze: list[Path],
    ) -> None:
        """
        Apply the codemod to the given list of files

        This method is responsible for orchestrating the application of the codemod to a given list of files.

        It will first apply the detector (if any) to the files to determine which files should be modified.

        It then applies the transformer pipeline to each file applicable file, potentially generating a change set.

        All results are then processed and reported to the context.

        Per-file processing can be parallelized based on the `max_workers` setting.

        :param context: The codemod execution context
        :param files_to_analyze: The list of files to analyze
        """
        self._apply(context, files_to_analyze, [self.name])

    def _process_file(
        self,
        filename: Path,
        context: CodemodExecutionContext,
        results: ResultSet | None,
        rules: list[str],
    ):
        line_exclude = file_line_patterns(filename, context.path_exclude)
        line_include = file_line_patterns(filename, context.path_include)
        findings_for_rule = None
        if results is not None:
            findings_for_rule = []
            for rule in rules:
                findings_for_rule.extend(
                    results.results_for_rule_and_file(context, rule, filename)
                )

        file_context = FileContext(
            context.directory,
            filename,
            line_exclude,
            line_include,
            findings_for_rule,
        )

        # TODO: for SAST tools we should preemtively filter out files that are not part of the result set

        if change_set := self.transformer.apply(
            context, file_context, findings_for_rule
        ):
            file_context.add_result(change_set)

        return file_context
