import uuid

from flask import (abort, flash, g, redirect, render_template, request,
                   session, url_for)
from oauth2client import client as oauth
import requests

try:
    from urllib.parse import urlencode
except:
    from urllib import urlencode

from globus_sdk import TransferClient, TransferAPIError

from mrdp import app, database, datasets
from mrdp.decorators import authenticated
from mrdp.utils import basic_auth_header, get_safe_redirect


@app.route('/', methods=['GET'])
def home():
    """Home page - play with it if you must!"""
    return render_template('home.jinja2')


@app.route('/signup', methods=['GET'])
def signup():
    """Send the user to Globus Auth with signup=1."""
    return redirect(url_for('authcallback', signup=1))


@app.route('/login', methods=['GET'])
def login():
    """
    Add code here to:

    - Redirect user to Globus Auth
    - Get an access token and a refresh token
    - Store these tokens in the session
    - Redirect to the repository page or profile page
      if this is the first login
    """
    return redirect(url_for('authcallback'))


@app.route('/logout', methods=['GET'])
@authenticated
def logout():
    """
    Add code here to:

    - Destroy Globus Auth token (remove it from session?)
    - ???
    """
    headers = {'Authorization': basic_auth_header()}
    data = {
        'token_type_hint': 'refresh',
        'token': g.credentials.refresh_token
    }

    # Invalidate the tokens with Globus Auth
    requests.post(app.config['GA_REVOKE_URI'],
                  headers=headers,
                  data=data)

    # Destroy the session state
    session.clear()

    redirect_uri = url_for('home', _external=True)

    ga_logout_url = []
    ga_logout_url.append(app.config['GA_LOGOUT_URI'])
    ga_logout_url.append('?client={}'.format(app.config['GA_CLIENT_ID']))
    ga_logout_url.append('&redirect_uri={}'.format(redirect_uri))
    ga_logout_url.append('&redirect_name=MRDP Demo App')

    # Send the user to the Globus Auth logout page
    return redirect(''.join(ga_logout_url))


@app.route('/profile', methods=['GET', 'POST'])
@authenticated
def profile():
    """User profile information. Assocated with a Globus Auth identity."""
    if request.method == 'GET':
        identity_id = session.get('primary_identity')
        profile = database.load_profile(identity_id)

        if profile:
            name, email, project = profile

            session['name'] = name
            session['email'] = email
            session['project'] = project

        if request.args.get('next'):
            session['next'] = get_safe_redirect()

        return render_template('profile.jinja2')
    elif request.method == 'POST':
        name = session['name'] = request.form['name']
        email = session['email'] = request.form['email']
        project = session['project'] = request.form['project']

        database.save_profile(identity_id=session['primary_identity'],
                              name=name,
                              email=email,
                              project=project)

        flash('Thank you! Your profile has been successfully updated.')

        if 'next' in session:
            redirect_to = session['next']
            session.pop('next')
        else:
            redirect_to = url_for('profile')

        return redirect(redirect_to)


@app.route('/authcallback', methods=['GET'])
def authcallback():
    if 'error' in request.args:
        pass
        # handle error

    scopes = 'urn:globus:auth:scope:transfer.api.globus.org:all'
    config = app.config

    if request.args.get('signup'):
        authorize_uri = '{}?signup=1'.format(config['GA_AUTH_URI'])
    else:
        authorize_uri = config['GA_AUTH_URI']

    flow = oauth.OAuth2WebServerFlow(app.config['GA_CLIENT_ID'],
                                     scope=scopes,
                                     authorization_header=basic_auth_header(),
                                     redirect_uri=config['GA_REDIRECT_URI'],
                                     auth_uri=authorize_uri,
                                     token_uri=config['GA_TOKEN_URI'],
                                     revoke_uri=config['GA_REVOKE_URI'])

    if 'code' not in request.args:
        state = str(uuid.uuid4())

        auth_uri = flow.step1_get_authorize_url(state=state)

        session['oauth2_state'] = state

        return redirect(auth_uri)
    else:
        passed_state = request.args.get('state')

        if passed_state and passed_state == session.get('oauth2_state'):
            code = request.args.get('code')

            try:
                credentials = flow.step2_exchange(code)
            except Exception as err:
                return repr(err)
            else:
                session.pop('oauth2_state')

                id_token = credentials.id_token
                session.update(
                    credentials=credentials.to_json(),
                    is_authenticated=True,
                    primary_username=id_token.get('preferred_username'),
                    primary_identity=id_token.get('sub'),
                )

            return redirect(url_for('transfer'))


@app.route('/transfer', methods=['GET', 'POST'])
@authenticated
def transfer():
    """
    Add code here to:

    - Send to Globus to select a destination endpoint
    - Submit a Globus transfer request and get the task ID
    - Return to a transfer "status" page

    The target template expects a 'task_id' (str) and a
    'transfer_status' (dictionary) containing various details about the
    task. Since this route is called only once after a transfer request
    is submitted, it only provides a 'task_id'.
    """
    if request.method == 'GET':
        return render_template('transfer.jinja2', datasets=datasets)

    if request.method == 'POST':
        if not request.form.get('dataset'):
            flash('Please select at least one dataset.')
            return redirect(url_for('transfer'))

        params = {
            'method': 'POST',
            'action': url_for('submit_transfer', _external=True,
                              _scheme='https'),
            'filelimit': 0,
            'folderlimit': 1
        }

        browse_endpoint = 'https://www.globus.org/app/browse-endpoint?{}' \
            .format(urlencode(params))

        session['form'] = {
            'datasets': request.form.getlist('dataset')
        }

        return redirect(browse_endpoint)


@app.route('/submit-transfer', methods=['POST'])
@authenticated
def submit_transfer():
    globus_form = request.form

    selected = session['form']['datasets']
    filtered_datasets = [ds for ds in datasets if ds['id'] in selected]

    transfer = TransferClient(auth_token=g.credentials.access_token)

    source_endpoint_id = app.config['DATASET_ENDPOINT_ID']
    destination_endpoint_id = globus_form['endpoint_id']

    transfer_items = []
    for ds in filtered_datasets:
        source_path = ds['path']
        dest_path = globus_form['path']

        if globus_form.get('folder[0]'):
            dest_path += globus_form['folder[0]'] + '/'

        dest_path += ds['name'] + '/'

        transfer_items.append({
            'DATA_TYPE': 'transfer_item',
            'source_path': source_path,
            'destination_path': dest_path,
            'recursive': True
        })

    submission_id = transfer.get_submission_id().data['value']
    transfer_data = {
        'DATA_TYPE': 'transfer',
        'submission_id': submission_id,
        'source_endpoint': source_endpoint_id,
        'destination_endpoint': destination_endpoint_id,
        'label': globus_form.get('label') or None,
        'DATA': transfer_items
    }

    transfer.endpoint_autoactivate(source_endpoint_id)
    transfer.endpoint_autoactivate(destination_endpoint_id)
    task_id = transfer.submit_transfer(transfer_data).data['task_id']

    flash('Transfer request submitted successfully. Task ID: ' + task_id)

    return(redirect(url_for('transfer_status', task_id=task_id)))


@app.route('/graph', methods=['GET', 'POST'])
@authenticated
def graph():
    """
    Add code here to:

    - Read the year and the IDs of the datasets the user wants
    - Instantiate a Transfer client as the identity of the portal
    - `GET` the CSVs for the selected datasets via HTTPS server as the
      identity of the portal
    - Generate a graph SVG file for the precipitation (`PRCP`) and
      temperature (`TMIN`/`TMAX`) for the selected year and datasets
    - `PUT` the generated graphs onto the predefined share endpoint as
      the identity of the portal
    - Display a confirmation
    """

    if request.method == 'GET':
        return render_template('graph.jinja2', datasets=datasets)

    selected_ids = request.form.getlist('dataset')
    selected_datasets = [dataset for dataset in datasets
                         if dataset['id'] in selected_ids]
    selected_year = request.form.get('year')

    if not (selected_datasets and selected_year):
        flash("Please select at least one dataset and a year to graph.")
        return redirect(url_for('graph'))

    # FIXME Instead of using the user's token (`g.credentials.access_token`),
    # we want to use the portal's access token (retrieved via two-legged OAuth
    # for some Globus ID, e.g. `mrdpportaladmin`, or via a refresh token?) for
    # *all* the operations within this handler.
    auth_token = g.credentials.access_token
    auth_headers = dict(Authorization='Bearer ' + auth_token)
    transfer = TransferClient(auth_token=auth_token)

    source_ep = app.config['DATASET_ENDPOINT_ID']
    source_info = transfer.get_endpoint(source_ep).data
    source_https = source_info.get('https_server')

    dest_ep = app.config['GRAPH_ENDPOINT_ID']
    dest_info = transfer.get_endpoint(dest_ep).data
    dest_https = dest_info.get('https_server')
    dest_base = app.config['GRAPH_ENDPOINT_BASE']
    dest_path = '%sGraphs for %s/' % (dest_base, session['primary_username'])

    if not (source_https and dest_https):
        # FIXME Remove this temporary workaround once we have HTTPS endpoints.
        #
        # flash("Both dataset and graph endpoints must be HTTPS endpoints.")
        # return redirect(url_for('graph'))
        source_https = source_https or 'https://mrdp-demo.appspot.com'
        dest_https = dest_https or 'https://mrdp-demo.appspot.com'

    # TODO Externalize the downloading of the CSVs and the generation of the
    # graphs, as conference participants won't necessarily find that part
    # interesting or relevant.

    from csv import reader
    from datetime import date
    from pygal import Line

    svgs = {}
    x_labels = [date(2016, month, 1).strftime('%B') for month in range(1, 13)]

    for dataset in selected_datasets:
        source_path = dataset['path']
        response = requests.get('%s/%s/%s.csv' % (source_https, source_path,
                                                  selected_year),
                                headers=auth_headers)
        csv = reader(response.iter_lines())

        header = next(csv)
        date_index = header.index('DATE')
        prcp_index = header.index('PRCP')
        tmin_index = header.index('TMIN')
        tmax_index = header.index('TMAX')

        monthlies = [dict(days_of_data=0, precipitation_total=0,
                          min_temperature_total=0, max_temperature_total=0)
                     for _ in range(12)]
        for row in csv:
            month = int(row[date_index][4:6])
            data = monthlies[month - 1]
            data['days_of_data'] += 1
            data['precipitation_total'] += int(row[prcp_index])
            data['min_temperature_total'] += int(row[tmin_index])
            data['max_temperature_total'] += int(row[tmax_index])

        graph = Line(x_labels=x_labels, x_label_rotation=90)
        graph.add("Precip(mm)", [monthly['precipitation_total'] / 10.
                                 for monthly in monthlies])
        graph.config.title = "%s from %s for %s" % \
                             ("Precipitation", dataset['name'], selected_year)
        svgs[graph.config.title] = graph.render()

        # TODO Switch this to a box plot to be more interesting?
        graph = Line(x_labels=x_labels, x_label_rotation=90)
        graph.add("Avg High(C)", [monthly['max_temperature_total'] / 10. /
                                  monthly['days_of_data']
                                  for monthly in monthlies])
        graph.add("Avg Low(C)", [monthly['min_temperature_total'] / 10. /
                                 monthly['days_of_data']
                                 for monthly in monthlies])
        graph.config.title = "%s from %s for %s" % \
                             ("Temperatures", dataset['name'], selected_year)
        svgs[graph.config.title] = graph.render()

    transfer.endpoint_autoactivate(dest_ep)

    try:
        transfer.operation_mkdir(dest_ep, dest_path)
    except TransferAPIError as error:
        if 'MkdirFailed.Exists' not in error.code:
            raise

    # TODO The portal identity should be setup with access manager privileges
    # on the graph destination endpoint.
    #
    # try:
    #     transfer.add_endpoint_acl_rule(
    #         dest_ep,
    #         dict(principal=session['primary_identity'],
    #              principal_type='identity', path=dest_path, permissions='r'),
    #     )
    # except TransferAPIError as error:
    #     if error.code != 'Exists':
    #         raise

    for filename, svg in svgs.items():
        # TODO Does the HTTPS server throw an error for an already-existing
        # destination file, or is it silently overwritten?
        requests.put('%s%s%s.svg' % (dest_https, dest_path, filename),
                     headers=auth_headers, data=svg)

    # TODO Instead of doing this, show a file list of the SVGs that were
    # generated and a link to "open in Transfer" that will open the directory
    # in Transfer Files page in the webapp
    flash("%d-file SVG upload to %s on %s completed!" %
          (len(svgs), dest_path, dest_info['display_name']))
    return redirect(url_for('graph'))


@app.route('/browse/<dataset_id>', methods=['GET'])
@authenticated
def browse(dataset_id):
    """
    Add code here to:

    - Get list of files for the selected dataset
    - Return a list of files to a browse view

    The target template (browse.jinja2) expects a unique dataset
    identifier 'dataset_id' (str) and 'file_list' (list of
    dictionaries) containing the following information about each file
    in the dataset:

    {'name': 'file name', 'size': 'file size', 'id': 'file uri/path'}

    'dataset_uri' is passed to the route in the URL as 'target_uri'.

    If you want to display additional information about each file, you
    must add those keys to the dictionary and modify the browse.jinja2
    template accordingly.
    """

    filtered_datasets = [ds for ds in datasets if ds['id'] == dataset_id]

    if len(filtered_datasets):
        dataset = filtered_datasets[0]
    else:
        abort(404)

    endpoint_id = app.config['DATASET_ENDPOINT_ID']
    path = dataset['path']

    transfer = TransferClient(auth_token=g.credentials.access_token)

    try:
        transfer.endpoint_autoactivate(endpoint_id)
        res = transfer.operation_ls(endpoint_id, path=path)
    except TransferAPIError as err:
        flash('Error [{}]: {}'.format(err.code, err.message))
        return redirect(url_for('transfer'))
    else:
        listing = res.data['DATA']

    file_list = [e for e in listing if e['type'] == 'file']

    ep = transfer.get_endpoint(endpoint_id).data

    dataset_uri = '{}/{}'.format(ep.get('https_server') or
                                 'https://mrdp-demo.appspot.com',  # FIXME
                                 path)

    return render_template('browse.jinja2', dataset_uri=dataset_uri,
                           file_list=file_list)


@app.route('/status/<task_id>', methods=['GET'])
@authenticated
def transfer_status(task_id):
    """
    Add code here to call Globus to get status/details of transfer with
    task_id.

    The target template (tranfer_status.jinja2) expects a 'task_id'
    (str) and a 'transfer_status' (dictionary) containing various
    details about the task. 'transfer_status' is expected to contain the
    following keys:

    {
        'source_ep_name': 'display name of source endpoint',
        'dest_ep_name': 'display name of destination endpoint',
        'request_time': time that the transfer request was submitted,
        'status': 'status of the transfer task',
        'files_transferred': number of files transferred so far,
        'fault': number of faults encountered,
    }

    'task_id' is passed to the route in the URL as 'task_id'.

    If you want to display additional information about the transfer,
    you must add those keys to the dictionary and modify the
    transfer_status.jinja2 template accordingly.
    """
    transfer = TransferClient(auth_token=g.credentials.access_token)
    task = transfer.get_task(task_id)

    return render_template('transfer_status.jinja2', task=task.data)
