"""
Setup script for compiling the custom C extension handler.

Usage:
    python setup.py build_ext --inplace
    python setup.py install
"""
from setuptools import setup, Extension

custom_handler_module = Extension(
    'custom_handler',
    sources=['custom_handler.c'],
    extra_compile_args=['-O2', '-Wall'],
)

setup(
    name='custom_handler',
    version='1.0.0',
    description='High-performance C extension logging handler',
    author='Example',
    ext_modules=[custom_handler_module],
    python_requires='>=3.6',
)
