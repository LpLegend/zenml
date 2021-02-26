#  Copyright (c) maiot GmbH 2021. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at:
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
#  or implied. See the License for the specific language governing
#  permissions and limitations under the License.
"""ZenML NLP Pipeline Prototype."""

import os
from typing import Dict, Text, Any, List, Optional, Union

import tensorflow as tf
from tfx.components.schema_gen.component import SchemaGen
from tfx.components.statistics_gen.component import StatisticsGen
from tfx.components.trainer.component import Trainer
from tfx.proto import trainer_pb2
from tokenizers.implementations import BertWordPieceTokenizer
from transformers import TFDistilBertForSequenceClassification

from zenml.core.backends.training.training_base_backend import \
    TrainingBaseBackend
from zenml.core.components.data_gen.component import DataGen
from zenml.core.components.split_gen.component import SplitGen
from zenml.core.components.tokenizer.component import Tokenizer
from zenml.core.pipelines.base_pipeline import BasePipeline
from zenml.core.standards import standard_keys as keys
from zenml.core.steps.split.base_split_step import BaseSplit
from zenml.core.steps.trainer.base_trainer import BaseTrainerStep
from zenml.utils import constants
from zenml.utils.enums import GDPComponent
from zenml.utils.enums import PipelineStatusTypes
from zenml.utils.post_training.post_training_utils import \
    get_feature_spec_from_schema
from zenml.utils.logger import get_logger

TOKENIZER = "tokenizer"

logger = get_logger(__name__)


class NLPPipeline(BasePipeline):
    PIPELINE_TYPE = "nlp"

    def __call__(self, sequence: Union[Text, List[Text]] = None):
        """Call operator for local inference method"""
        if not self.get_status() == PipelineStatusTypes.Succeeded.name:
            print("Please run the pipeline first before running inference!")

        model_uri = os.path.join(self.get_model_uri(), "serving_model_dir")
        model = TFDistilBertForSequenceClassification.from_pretrained(
            model_uri
        )

        vocab = os.path.join(self.get_tokenizer_uri(), "vocab.txt")
        tokenizer = BertWordPieceTokenizer(vocab=vocab)
        tokenizer.enable_padding(length=128)
        tokenizer.enable_truncation(max_length=128)

        encoded = tokenizer.encode(sequence=sequence)

        id_list = tf.train.Feature(
            int64_list=tf.train.Int64List(value=encoded.ids))
        attention_list = tf.train.Feature(
            int64_list=tf.train.Int64List(value=encoded.attention_mask))

        feature = {"input_ids": id_list,
                   "attention_mask": attention_list}

        serialized_ex = tf.train.Example(
            features=tf.train.Features(feature=feature)).SerializeToString()

        necessary_features = ["input_ids", "attention_mask"]
        example_spec = get_feature_spec_from_schema(self.get_schema_uri())
        feature_spec = {k: v for k, v in example_spec.items()
                        if k in necessary_features}

        # transform is trivial so we can parse the spec anyways
        parsed_features = tf.io.parse_example(serialized_ex,
                                              feature_spec)

        transformed_bert_features = {k: tf.reshape(v, (1, -1)) for k, v in
                                     parsed_features.items()
                                     if k in necessary_features}

        prediction = model(input_ids=transformed_bert_features["input_ids"],
                           training=False)

        print(prediction)

    def get_tfx_component_list(self, config: Dict[Text, Any]) -> List:
        """
        Builds the NLP pipeline as a series of TFX components.

        Args:
            config: A ZenML configuration in dictionary format.

        Returns:
            A chronological list of TFX components making up the NLP
             pipeline.

        """
        steps = config[keys.GlobalKeys.PIPELINE][keys.PipelineKeys.STEPS]

        component_list = []

        ############
        # RAW DATA #
        ############
        data_config = steps[keys.TrainingSteps.DATA]
        data = DataGen(
            name=self.datasource.name,
            source=data_config[keys.StepKeys.SOURCE],
            source_args=data_config[keys.StepKeys.ARGS]
        ).with_id(GDPComponent.DataGen.name)

        #############
        # TOKENIZER #
        #############
        tokenizer_config = steps[TOKENIZER]
        tokenizer = Tokenizer(
            source=tokenizer_config[keys.StepKeys.SOURCE],
            source_args=tokenizer_config[keys.StepKeys.ARGS],
            examples=data.outputs.examples,
        ).with_id(TOKENIZER.capitalize())

        component_list.extend([tokenizer])

        # return component_list

        statistics_data = StatisticsGen(
            examples=tokenizer.outputs.output_examples
        ).with_id(GDPComponent.DataStatistics.name)

        schema_data = SchemaGen(
            statistics=statistics_data.outputs.output,
            infer_feature_shape=True,
        ).with_id(GDPComponent.DataSchema.name)

        split_config = steps[keys.TrainingSteps.SPLIT]
        splits = SplitGen(
            input_examples=tokenizer.outputs.output_examples,
            source=split_config[keys.StepKeys.SOURCE],
            source_args=split_config[keys.StepKeys.ARGS],
            schema=schema_data.outputs.schema,
            statistics=statistics_data.outputs.output,
        ).with_id(GDPComponent.SplitGen.name)

        component_list.extend([data,
                               statistics_data,
                               schema_data,
                               splits])

        ############
        # TRAINING #
        ############
        training_backend: Optional[TrainingBaseBackend] = \
            self.steps_dict[keys.TrainingSteps.TRAINER].backend

        # default to local
        if training_backend is None:
            training_backend = TrainingBaseBackend()

        training_kwargs = {
            'custom_executor_spec': training_backend.get_executor_spec(),
            'custom_config': steps[keys.TrainingSteps.TRAINER]
        }
        training_kwargs['custom_config'].update(
            training_backend.get_custom_config())

        trainer = Trainer(
            examples=splits.outputs.examples,
            run_fn=constants.TRAINER_FN,
            schema=schema_data.outputs.schema,
            train_args=trainer_pb2.TrainArgs(),
            eval_args=trainer_pb2.EvalArgs(),
            **training_kwargs
        ).with_id(GDPComponent.Trainer.name)

        component_list.extend([trainer])

        return component_list

    def steps_completed(self) -> bool:
        mandatory_steps = [TOKENIZER,
                           keys.TrainingSteps.TRAINER,
                           keys.TrainingSteps.DATA]

        for step_name in mandatory_steps:
            if step_name not in self.steps_dict.keys():
                raise AssertionError(f'Mandatory step {step_name} not added.')
        return True

    def add_tokenizer(self, tokenizer_step: Any):
        self.steps_dict[TOKENIZER] = tokenizer_step

    def add_split(self, split_step: BaseSplit):
        self.steps_dict[keys.TrainingSteps.SPLIT] = split_step

    def add_trainer(self, trainer_step: BaseTrainerStep):
        self.steps_dict[keys.TrainingSteps.TRAINER] = trainer_step

    def get_model_uri(self):
        """Gets model artifact."""
        uris = self.get_artifacts_uri_by_component(
            GDPComponent.Trainer.name, False)
        return uris[0]

    def get_schema_uri(self):
        """Gets transform artifact."""
        uris = self.get_artifacts_uri_by_component(
            GDPComponent.DataSchema.name, False)
        return uris[0]

    def get_tokenizer_uri(self):
        """Gets transform artifact."""
        uris = self.get_artifacts_uri_by_component(
            TOKENIZER.capitalize(), False)
        return uris[0]
