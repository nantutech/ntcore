from queue import Queue

from .models.experiment import Experiment
from .resources.api_client import ApiClient
from .integrations.utils import get_runtime_version
import json, base64, pickle, tarfile, tempfile
import sklearn
import tensorflow as tf
import torch

class Client(object):
    '''
    A Python interface for the NTCore API.
    :param username:
        The username of this API user.
    :param password:
        The password of this API user.
    :param programToken:
        The token for the program this user is accessing.
    :param server:
        Your UAT or Production API URL if applicable.
    :param encryptionData:
        Dictionary with params for encrypted requests (keys: clientPrivateKeySetLocation, keySetLocation, etc).
    .. note::
        **server** defaults to the NTCore Sandbox URL if not provided.
    '''

    def __init__(self,
                 username=None,
                 password=None,
                 program_token=None,
                 server="http://localhost:8000/",
                 encryption_data=None):
        '''
        Create an instance of the API interface.
        This is the main interface the user will call to interact with the API.
        '''
        self._username = username
        self._password = password
        self._program_token = program_token
        self._server = server
        self._queue = Queue()
        self._api_client = ApiClient(self._username, self._password, self._server, encryption_data)

    def create_workspace(self, name):
        '''
        Creates a new workspace with the given name.
        '''
        return self._api_client.doPost(self.__build_url('workspace'), dict(type = "API", name = name))

    def get_workspace(self, workspace_id):
        '''
        Retrieves metadata of a workspace with the given id.
        '''
        return self._api_client.doGet(self.__build_url('workspace', workspace_id))

    def list_workspaces(self):
        '''
        Retrieves metadata of all the available workspaces.
        '''
        return self._api_client.doGet(self.__build_url('workspaces'))

    def delete_workspace(self, workspace_id):
        '''
        Deletes a given workspace with the given id.
        '''
        return self._api_client.doDel(self.__build_url('workspace', workspace_id))

    def register_experiment(self, workspace_id, version):
        '''
        Register an experiment with the given workspace id and model version.
        '''
        return self._api_client.doPost(self.__build_url('workspace', workspace_id, 'registry'), {"version": version})

    def get_registered_experiment(self, workspace_id):
        '''
        Retrieves the registered experiment for a workspace.
        '''
        return self._api_client.doGet(self.__build_url('workspaces', workspace_id, 'registry'))

    def unregister_experiment(self, workspace_id):
        '''
        Unregister an experiment with the given workspace id and model version.
        '''
        return self._api_client.doDel(self.__build_url('workspace', workspace_id, 'registry'))

    def deploy_model(self, workspace_id, version):
        '''
        Deploy a trained model as API based on the given workspace id and version.
        '''
        return self._api_client.doPost(self.__build_url('workspace', workspace_id, 'model', str(version), 'deploy'), data={})
    
    def download_model(self, workspace_id, version):
        '''
        Deploy a trained model as API based on the given workspace id and version.
        '''
        return self._api_client.doGet(self.__build_url('workspace', workspace_id, 'model', str(version)))

    def start_run(self, workspace_id):
        '''
        Starts a new experiment run with given workspace id.
        '''
        experiment = Experiment(self, workspace_id)
        self._queue.put(experiment)
        return experiment

    def log_pretraining_metadata(self, metadata: dict):
        '''
        Logs the metadata before training.
        '''
        if len(self._queue) == 0:
            raise ValueError('No active experiment')
        self._queue[0].pretraining_metadata = metadata

    def log_posttraining_metadata(self, metadata):
        '''
        Logs the metadata after training.
        '''
        if len(self._queue) == 0:
            raise ValueError('No active experiment')
        self._queue[0].posttraining_metadata = metadata

    def save_model(self, model):
        '''
        Emits the metadata and serialized model to NTCore server.
        '''
        experiment: Experiment = self._queue.get()
        workspace_id = experiment.workspace_id
        if workspace_id is None:
            raise ValueError('Workspace id is required')

        serialized_model, model_file, framework = self.__serialize_model(model)
        payload = dict(
            runtime = get_runtime_version(),
            framework = framework,
            parameters = json.dumps(experiment.pretraining_metadata).encode('utf-8'),
            metrics = json.dumps(experiment.posttraining_metadata).encode('utf-8'),
            model = base64.b64encode(serialized_model))
        
        print(model_file.name)
        return self._api_client.doPost(self.__build_url('workspace', workspace_id, 'experiment'), payload)

    def __serialize_model(self, model):
        '''
        Serializes model to bytes.
        '''
        if isinstance(model, sklearn.base.BaseEstimator):
            return pickle.dumps(model), None, 'sklearn'
        elif isinstance(model, tf.keras.Model):
            with tempfile.TemporaryDirectory() as model_dir:
                model.save(model_dir)
                model_file = tempfile.NamedTemporaryFile(suffix='.tar.gz')
                buffer = tarfile.open(model_file.name, "w:gz")
                buffer.add(model_dir, arcname="model")
                buffer.close()
            return open(model_file.name, "rb").read(), model_file, 'tensorflow'
        elif isinstance(model, torch.nn.Module):
            ### Saving and loading extra files
            # extra_files = {'transform': pickle.dumps(transform)}
            # model_script.save('model_script.pt', _extra_files=extra_files)
            # extra_files = {'transform': None}
            # model = torch.jit.load('model_script.pt', _extra_files=extra_files)
            # transform = pickle.loads(extra_files['transform'])
            model_file = tempfile.NamedTemporaryFile(suffix='.pt')
            buffer = torch.jit.script(model)
            buffer.save(model_file.name)
            return open(model_file.name, "rb").read(), model_file, 'pytorch'

    def __build_url(self, *paths):
        """
        Returns the NTCore endpoint for sending experiment data.
        """
        return '/'.join(s.strip('/') for s in paths)