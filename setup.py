from setuptools import setup

VERSION = '2.0.2'


def readme():
    with open('README.md') as f:
        return f.read()


setup(
    name='tempermonitor',
    version=VERSION,
    description='Tempermonitor sensor temperature reading deamon',
    long_description=readme(),
    url='http://gitlab.stusta.de/stustanet/temperature-daemon',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.7',
        'Operating System :: POSIX :: Linux'
    ],
    install_requires=[
        'asyncio',
        'pyserial-asyncio',
        'prometheus_client'
    ],
    license='MIT',
    packages=['tempermonitor'],
    include_package_data=True,
    zip_safe=False
)
