import numpy as np
import tensorflow as tf

from bot_code.models.base_agent_model import BaseAgentModel


class BaseLSTMModel(BaseAgentModel):
    num_epochs = 100
    num_actions = 8
    total_series_length = 50000
    truncated_backprop_length = 15
    echo_step = 3
    hidden_size = 219
    stored_data = []
    stored_data_length = 200
    static_state_dim = 0
    def __init__(self,
                 session,
                 num_actions,
                 input_formatter_info=[0, 0],
                 player_index=-1,
                 action_handler=None,
                 is_training=False,
                 optimizer=tf.train.GradientDescentOptimizer(learning_rate=0.1),
                 summary_writer=None,
                 summary_every=100,
                 config_file=None):

        self.num_actions = num_actions
        print ('lstm', 'num_actions', num_actions)
        if input_formatter_info is None:
            input_formatter_info = [0, 0]
        super().__init__(session, num_actions,
                         input_formatter_info=input_formatter_info,
                         player_index=player_index,
                         action_handler=action_handler,
                         is_training=is_training,
                         optimizer=optimizer,
                         summary_writer=summary_writer,
                         summary_every=summary_every,
                         config_file=config_file)

        self.static_state_dim = self.state_dim

    def _create_model(self, model_input, batch_size):
        self.create_weights()
        if self.is_training:
            input_ = tf.split(model_input, 200, 0)
        else:
            input_ = tf.split(model_input, 1, 0)
        # input_ = self.input_encoder(model_input)
        # input_ = tf.nn.xw_plus_b(model_input, self.weights['h1'], self.biases['b1'])
        # input_ = tf.unstack(model_input, self.stored_data_length, 0)
        # Forward passes
        cell = tf.nn.rnn_cell.BasicLSTMCell(self.state_dim)
        # defining initial state
        # initial_state = cell.zero_state(batch_size, dtype=tf.float32)
        with tf.variable_scope('recurrent_layer', reuse=tf.AUTO_REUSE):
            outputs, states = tf.nn.static_rnn(cell, input_, dtype=tf.float32)
        output = tf.reshape(outputs, [-1, self.hidden_size])
        self.logits = self.rnn_decoder(output)
        return self.action_handler.create_model_output(self.logits), self.logits

    def create_input_array(self, game_tick_packet, frame_time):
        data = self.input_formatter.create_input_array(game_tick_packet, frame_time)
        if len(self.stored_data) == self.stored_data_length:
            del self.stored_data[0]
        self.stored_data.append(data)
        self.state_dim = len(self.stored_data)
        return self.stored_data

    def acreate_batched_inputs(self, inputs):
        def chunks(l, n, offset):
            """Yield successive n-sized chunks from l."""
            for i in range(0, len(l), offset):
                yield l[i:i + n]

        safe = chunks(inputs[0], self.stored_data_length, int(self.stored_data_length / 2))
        labels = chunks(inputs[1], self.stored_data_length, int(self.stored_data_length / 2))
        return safe, labels

    def create_weights(self):
        self.weights = {
            'h1': tf.Variable(np.random.rand(self.state_feature_dim, self.hidden_size), dtype=tf.float32),
            'h2': tf.Variable(np.random.rand(self.hidden_size, self.hidden_size), dtype=tf.float32),
            'out': tf.Variable(np.random.rand(self.hidden_size, self.num_actions), dtype=tf.float32),
        }
        self.biases = {
            'b1': tf.Variable(np.random.rand(self.hidden_size), dtype=tf.float32, name='b1'),
            'b2': tf.Variable(np.random.rand(self.hidden_size), dtype=tf.float32, name='b2'),
            'out': tf.Variable(np.random.rand(self.num_actions), dtype=tf.float32, name='out')
        }
        self.add_saver('vars',
                       tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES))

    def _create_variables(self):
        super()._create_variables()
        self.labels = tf.placeholder(tf.float32,
                                     (None, self.action_handler.get_number_actions()),
                                     name="taken_actions_phd")

    def sample_action(self, input_state):
        """
        Runs the model to get a single action that can be returned.
        :param input_state: This is the current state of the model at this point in time.
        :return:
        A sample action that can then be used to get controller output.
        """
        action = self.sess.run(self.get_agent_output(), feed_dict=self.create_sampling_feed_dict(input_state))
        print (np.array(action)[:, -1], self.stored_data[0][7])
        return np.array(action)[:, -1]


    def input_encoder(self, input):
        inputs = tf.nn.relu(tf.add(tf.matmul(input, self.weights['h1']), self.biases['b1']), name='input_layer')
        return inputs

    def rnn_decoder(self, rnn_out):
        # Encoder Hidden layer with sigmoid activation #2
        hidden_layer_1 = tf.nn.relu(tf.add(tf.matmul(rnn_out, self.weights['h2']), self.biases['b2']), name='rnn_out')

        # Encoder Hidden layer with sigmoid activation #3
        return tf.nn.sigmoid(tf.add(tf.matmul(hidden_layer_1, self.weights['out']), self.biases['out']), name='logits')

    def _create_split_training_op(self, indexes, logits, labels, *args):
        if len(labels.get_shape()) == 2:
            labels = tf.squeeze(labels, axis=[1])
        cross_entropy = self.action_handler.get_action_loss_from_logits(
            labels=labels, logits=logits, index=indexes)
        loss = tf.reduce_mean(cross_entropy, name='xentropy_mean' + str(indexes))

        tf.summary.scalar("loss", tf.reduce_mean(loss))

        return loss

    def _process_results(self, central_result, split_result):
        total_loss = 0.0
        for loss in split_result:
            total_loss += loss

        tf.summary.scalar("total_loss", total_loss)
        return self.optimizer.minimize(total_loss)

    def _create_central_training_op(self, predictions, logits, raw_model_input, labels):
        return None

    def get_model_name(self):
        return 'rnn' + ('_split' if self.action_handler.is_split_mode else '')

    def get_labels_placeholder(self):
        return self.labels
