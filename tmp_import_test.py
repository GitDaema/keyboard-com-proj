import importlib.util
spec = importlib.util.spec_from_file_location('rgb_controller','src/rgb_controller.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
print('connect:', hasattr(m,'connect'))
print('disconnect:', hasattr(m,'disconnect'))
print('get_key_color:', hasattr(m,'get_key_color'))
print('set_key_color:', hasattr(m,'set_key_color'))
print('init_all_keys:', hasattr(m,'init_all_keys'))
