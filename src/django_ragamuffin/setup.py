from setuptools import setup, find_packages

setup(
    name='django_ragamuffin',  # Your app name
    version='0.1.0',  # Initial version
    packages=find_packages(),
    include_package_data=True,  # Important for static files/migrations
    license='MIT License',  # Choose your license
    description='A Django app for ...',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    url='https://github.com/opentaproject/django_openailite',
    author='Stellan Östlund',
    author_email='stellan.ostlund@gmail.com',
    classifiers=[
        'Environment :: Web Environment',
        'Framework :: Django',
        'Framework :: OpenAI API',
        'Framework :: Django :: 5.2',  # Update as appropriate
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.11.1',
    ],
    install_requires=[
        'Django>=5.2',  # Specify Django version requirements
        'openai==1.74.0'
    ],
    python_requires='>=3.11',  # Adjust as needed
)
