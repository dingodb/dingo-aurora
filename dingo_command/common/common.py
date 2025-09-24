from keystoneauth1 import loading as ks_loading
from oslo_config import cfg
import inspect
import datetime

import os  # Move import to module level

_ADAPTER_VERSION_OPTS = ('version', 'min_version', 'max_version')


def get_ksa_adapter_opts(default_service_type, deprecated_opts=None):
    """Get auth, Session, and Adapter conf options from keystonauth1.loading.

    :param default_service_type: Default for the service_type conf option on
                                 the Adapter.
    :param deprecated_opts: dict of deprecated opts to register with the ksa
                            Adapter opts.  Works the same as the
                            deprecated_opts kwarg to:
                    keystoneauth1.loading.session.Session.register_conf_options
    :return: List of cfg.Opts.
    """
    opts = ks_loading.get_adapter_conf_options(include_deprecated=False,
                                               deprecated_opts=deprecated_opts)

    for opt in opts[:]:
        # Remove version-related opts.  Required/supported versions are
        # something the code knows about, not the operator.
        if opt.dest in _ADAPTER_VERSION_OPTS:
            opts.remove(opt)

    # Override defaults that make sense for nova
    cfg.set_defaults(opts,
                     valid_interfaces=['internal', 'public'],
                     service_type=default_service_type)
    return opts

def _dummy_opt(name):
    # A config option that can't be set by the user, so it behaves as if it's
    # ignored; but consuming code may expect it to be present in a conf group.
    return cfg.Opt(name, type=lambda x: None)

def register_ksa_opts(conf, group, default_service_type, include_auth=True,
                      deprecated_opts=None):
    """Register keystoneauth auth, Session, and Adapter opts.

    :param conf: oslo_config.cfg.CONF in which to register the options
    :param group: Conf group, or string name thereof, in which to register the
                  options.
    :param default_service_type: Default for the service_type conf option on
                                 the Adapter.
    :param include_auth: For service types where Nova is acting on behalf of
                         the user, auth should come from the user context.
                         In those cases, set this arg to False to avoid
                         registering ksa auth options.
    :param deprecated_opts: dict of deprecated opts to register with the ksa
                            Session or Adapter opts.  See docstring for
                            the deprecated_opts param of:
                    keystoneauth1.loading.session.Session.register_conf_options
    """
    # ksa register methods need the group name as a string.  oslo doesn't care.
    group = getattr(group, 'name', group)
    ks_loading.register_session_conf_options(
        conf, group, deprecated_opts=deprecated_opts)
    if include_auth:
        ks_loading.register_auth_conf_options(conf, group)
    conf.register_opts(get_ksa_adapter_opts(
        default_service_type, deprecated_opts=deprecated_opts), group=group)
    # Have to register dummies for the version-related opts we removed
    # for name in _ADAPTER_VERSION_OPTS:
    #     conf.register_opt(_dummy_opt(name), group=group)


def dingo_print(*args, **kwargs):
    """
    Enhanced print function that adds timestamp, file name, line number, and function name information.
    
    This function works exactly like the built-in print function but prefixes
    the output with the current timestamp, file name, line number, and function name.
    
    Args:
        *args: Variable length argument list (same as print)
        **kwargs: Arbitrary keyword arguments (same as print)
    """
    # Get caller information (optimize: get frame once and extract all info)
    frame = inspect.currentframe().f_back
    line_number = frame.f_lineno
    function_name = frame.f_code.co_name
    file_name = os.path.basename(frame.f_code.co_filename)
    
    # Get current timestamp (optimize: use faster formatting)
    now = datetime.datetime.now()
    current_time = f"{now.year}-{now.month:02d}-{now.day:02d} {now.hour:02d}:{now.minute:02d}:{now.second:02d}.{now.microsecond//1000:03d}"
    
    # Create prefix with timestamp, file name, line number, and function name
    prefix = f"[{current_time}] [{file_name}] [Line {line_number}] [{function_name}]"
    
    # If there are arguments to print
    if args:
        # Convert first argument to string and prepend prefix
        first_arg = f"{prefix} {args[0]}"
        # Call original print with modified first argument and remaining args
        print(first_arg, *args[1:], **kwargs)
    else:
        # If no arguments, just print the prefix
        print(prefix, **kwargs)