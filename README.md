# rackit

`rackit` - **R**EST **A**PI **C**lient Tool**kit** - is a toolkit for building clients for
REST APIs.

It is not intended to provide a fully-functional API client out of the box, but instead provides
simple building blocks for assembling clients for REST APIs. These clients support advanced
features such as attribute aliases, caching, lazy-loading, nested resources and embedded
resources.

`rackit` uses the excellent [requests](https://requests.readthedocs.io/en/master/) library under
the hood - familiarity with this library will be useful in order to use the base classes from
`rackit`.

## Installation

Currently, `rackit` must be installed directly from GitHub:

```sh
pip install git+https://github.com/cedadev/rackit.git
```

## Base classes

`rackit` provides a number of base classes that can be used to assemble an API client:

  * Subclasses of `rackit.Connection` determine how API requests should be made, including authentication.
  * Subclasses of `rackit.ResourceManager` are responsible for managing resource instances, including
    handling pagination and the extraction of data from responses.
  * Subclasses of `rackit.Resource` are used to define properties for each available resource.
    Instances of subclasses of this class are returned by managers to represent resources on the server.
  * `RootResource`, `NestedResource`, `EmbeddedResource` and `EmbeddedResourceList` are used to
    connect resources to the connection and to each other.

## Worked example - GitHub API

This example walks through the process of creating an API client for the
[GitHub API](https://developer.github.com/v3/).

To start with, let's configure the Python [logging](https://docs.python.org/3.7/library/logging.html)
module so that we can see the API requests as they happen. `rackit.Connection` will output information
about the requests it is making at the level `DEBUG` using the `rackit.connection` logger:

```python
import logging
logger = logging.getLogger('rackit.connection')
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler())
```

## Authentication

The base classes in `rackit` make no authentication decisions at all, as this differs so
widely between APIs.

As well as the base URL for the API, `rackit.Connection` expects to be provided with a
[requests Session object](https://requests.readthedocs.io/en/master/user/advanced/#session-objects)
that is pre-configured to use whatever authentication is required to access the API you are
consuming. This can be done by setting default headers for the session or by using a
[custom authentication object](https://requests.readthedocs.io/en/master/user/advanced/#custom-authentication).

Here, we demonstrate the use of a custom authentication object to configure GitHub authentication
using a [personal access token](https://help.github.com/en/github/authenticating-to-github/creating-a-personal-access-token-for-the-command-line):

```python
import requests

from rackit import Connection


class GitHubAuth(requests.auth.AuthBase):
    def __init__(self, token):
        self.token = token

    def __call__(self, request):
        # Add the correctly formatted header to the request
        request.headers['Authorization'] = "token {}".format(self.token)
        return request


class GitHub(Connection):
    GITHUB_API = "https://api.github.com"

    def __init__(self, token):
        # Initialise a requests session that uses the token auth
        session = requests.Session()
        session.auth = GitHubAuth(token)
        super().__init__(self.GITHUB_API, session)
```

To prove that the authentication works, use the connection to print the authenticated user:

```python
github = GitHub('GITHUB_PERSONAL_ACCESS_TOKEN')
print(github.api_get('/user').json())
#> API request: GET https://api.github.com/user
#> {'avatar_url': 'https://avatars1.githubusercontent.com/u/13452123?v=4',
#   ...
#   'login': 'mkjpryor-stfc',
#   'name': 'Matt Pryor',
#   ...
#   'url': 'https://api.github.com/users/mkjpryor-stfc'}
```

## Defining resources

To define the available resources for an API, just subclass `rackit.Resource`. The resource
is then attached to the connection using `rackit.RootResource`.

As an example, let's add a resource for accessing repositories on GitHub. The GitHub API
is unusual in that it does not use URLs of the format `/repos[/id]` to access repositories.
Rather, it uses URLs of the form `/repos/:owner/:repo`. However, it is possible to configure
`rackit` to handle these URLs by overriding the primary key for the resource:

The GitHub API is also unusual in that it doesn't allow all the repositories to be listed
using `/repos`. Instead, repositories can be listed for the authenticated user (`/user/repos`),
for a user (`/users/:username/repos`) or for an organisation (`/orgs/:org/repos`). To support
this, we can use a custom manager:

```python
from rackit import Connection, Resource, ResourceManager, RootResource


class RepositoryManager(ResourceManager):
    def for_authenticated_user(self, **params):
        return self._fetch_all("/user/repos", **params)

    def for_user(self, username, **params):
        return self._fetch_all("/user/{}/repos".format(username), **params)

    def for_org(self, org, **params):
        return self._fetch_all("/orgs/{}/repos".format(org), **params)


class Repository(Resource):
    class Meta:
        manager_cls = RepositoryManager
        endpoint = "/repos"
        primary_key_field = "full_name"


class GitHub(Connection):
    # ...
    repos = RootResource(Repository)
```

Now let's use the connection to count the repos for the `cedadev` org. All the listing methods
return generators - this is important when pagination is involved as it potential avoids expensive
additional network requests:

```python
repo_count = len(list(github.repos.for_org("cedadev")))
print(repo_count)
#> API request: GET https://api.github.com/orgs/cedadev/repos
#> 30
```

## Pagination

`cedadev` has way more than 30 repositories, so why does the statement above return 30? We are
only considering the first page (the default page size in GitHub is 30)!

We need to implement pagination in our client. Like authentication, the method for pagination varies
widely across APIs, so `rackit` doesn't do any pagination by default. However it does provide a
simple hook for implementing pagination by overriding `ResourceManager.extract_list`. This method
receives the `requests` response object and returns a tuple of `(list of data, url for next page)`.

GitHub uses [Link headers](https://developer.github.com/v3/#link-header) for pagination in their
API, so let's implement support for this using a custom resource manager. Luckily, `requests` has
[built-in support](https://requests.readthedocs.io/en/master/user/advanced/#link-headers) for `Link`
headers that we can leverage. Because this is common across all GitHub resources, let's implement
it in a common base class for all GitHub resource managers:

```python
class GitHubResourceManager(ResourceManager):
    def extract_list(self, response):
        # Extract the url for the next page from the Link header
        next_page = response.links.get('next', {}).get('url')
        return response.json(), next_page


class GitHubResource(Resource):
    class Meta:
        manager_cls = GitHubResourceManager


class RepositoryManager(GitHubResourceManager):
    # ... as before ...


class Repository(GitHubResource):
    # ... as before ...
```

Re-running the statement from above will now count all the repositories by fetching
multiple pages:

```python
repo_count = len(list(github.repos.for_org("cedadev")))
print(repo_count)
#> API request: GET https://api.github.com/orgs/cedadev/repos
#> API request: GET https://api.github.com/organizations/1781681/repos?page=2
#> API request: GET https://api.github.com/organizations/1781681/repos?page=3
#> API request: GET https://api.github.com/organizations/1781681/repos?page=4
#> API request: GET https://api.github.com/organizations/1781681/repos?page=5
#> API request: GET https://api.github.com/organizations/1781681/repos?page=6
#> API request: GET https://api.github.com/organizations/1781681/repos?page=7
#> API request: GET https://api.github.com/organizations/1781681/repos?page=8
#> API request: GET https://api.github.com/organizations/1781681/repos?page=9
#> API request: GET https://api.github.com/organizations/1781681/repos?page=10
#> API request: GET https://api.github.com/organizations/1781681/repos?page=11
#> 307
```

## Using nested resources

Let's say that we wanted to enable a syntax like this:

```python
cedadev_repos = github.orgs.get("cedadev").repos.all()
```

This is much nicer than adding custom methods to the repository manager. We can do this by adding
an `Organization` resource and using the support for nested resources in `rackit`. Doing so would
also enable us to remove the clumsy `for_org` method of the `RepositoryManager`:

```python
class Organization(GitHubResource):
    class Meta:
        endpoint = "/orgs"
        primary_key_field = "login"

    repos = NestedResource(Repository)


class GitHub(Connection):
    # ...
    repos = RootResource(Repository)
    orgs = RootResource(Organization)
```

We can see that this returns the same result as before, but with a nicer, fluent interface:

```python
cedadev_repos = github.orgs.get("cedadev").repos.all()
print(len(list(cedadev_repos)))
#> API request: GET https://api.github.com/orgs/cedadev/repos
#> API request: GET https://api.github.com/organizations/1781681/repos?page=2
#> API request: GET https://api.github.com/organizations/1781681/repos?page=3
#> API request: GET https://api.github.com/organizations/1781681/repos?page=4
#> API request: GET https://api.github.com/organizations/1781681/repos?page=5
#> API request: GET https://api.github.com/organizations/1781681/repos?page=6
#> API request: GET https://api.github.com/organizations/1781681/repos?page=7
#> API request: GET https://api.github.com/organizations/1781681/repos?page=8
#> API request: GET https://api.github.com/organizations/1781681/repos?page=9
#> API request: GET https://api.github.com/organizations/1781681/repos?page=10
#> API request: GET https://api.github.com/organizations/1781681/repos?page=11
#> 307
```

Let's also replace the `for_user` method by defining a `User` resource:

```python
class User(GitHubResource):
    class Meta:
        endpoint = "/users"
        primary_key_field = "login"

    repos = NestedResource(Repository)


class GitHub(Connection):
    # ...
    repos = RootResource(Repository)
    orgs = RootResource(Organization)
    users = RootResource(User)
```

```python
mkjpryor_repos = github.users.get("mkjpryor-stfc").repos.all()
print(len(list(mkjpryor_repos)))
#> API request: GET https://api.github.com/users/mkjpryor-stfc/repos
#> 10
```

## Advanced usage - custom attributes

Let's see if we can replace the final custom method on our `RepositoryManager` - `for_authenticated_user`.
This is slightly more involved as it doesn't involve a manager (the endpoint doesn't really conform to
REST), but it is still possible quite easily by directly returning a resource instance:

```python
class GitHub(Connection):
    # ... as before ...

    @property
    def authenticated_user(self):
        # Return a user resource
        # We don't know any information about the user at this point, so give an empty
        # dictionary as the data and tell it to lazily load
        # Override the default path to use /user to load information when requested
        # This also means that /user rather than /users/:username is used as a prefix
        # when fetching nested resources
        return User(
            manager = self.users,
            data = dict(),
            partial = True,
            path = "/user"
        )
```

This allows us to do the following:

```python
my_repos = github.authenticated_user.repos.all()
print(len(list(my_repos)))
#> API request: GET https://api.github.com/user/repos
#> API request: GET https://api.github.com/user/repos?page=2
#> API request: GET https://api.github.com/user/repos?page=3
#> API request: GET https://api.github.com/user/repos?page=4
#> API request: GET https://api.github.com/user/repos?page=5
#> API request: GET https://api.github.com/user/repos?page=6
#> API request: GET https://api.github.com/user/repos?page=7
#> API request: GET https://api.github.com/user/repos?page=8
#> API request: GET https://api.github.com/user/repos?page=9
#> API request: GET https://api.github.com/user/repos?page=10
#> API request: GET https://api.github.com/user/repos?page=11
#> API request: GET https://api.github.com/user/repos?page=12
#> API request: GET https://api.github.com/user/repos?page=13
#> API request: GET https://api.github.com/user/repos?page=14
#> 399
```

## Creating, updating and deleting resources

Now we have our nested structure in place, we should be able to create, update and delete repositories
using it. Let's create a new repository for the authenticated user:

```python
repository = github.authenticated_user.repos.create(name = "my-test-repo")
print(repository)
#> API request: POST https://api.github.com/user/repos
#> __main__.Repository({
#   'id': 261995040,
#   'name': 'my-test-repo',
#   'full_name': 'mkjpryor-stfc/my-test-repo',
#   'private': False,
#   ...
#  })
```

We can also update a resource. This can be done in one of two ways, both of which return
a **new instance of the resource**. Once a resource instance exists, it is effectively immutable.

Using our GitHub example, the following statements make the equivalent update. However one requires
the resource instance to already exist, whereas the other requires only the identifier:

```python
# Directly on the resource instance
# This requires that the resource has previously been fetched
updated = repository._update(name = "test-update-name")

# Using the manager
updated = github.repos.update("mkjpryor-stfc/my-test-repo", name = "test-update-name")

print(updated)
#> API request: PATCH https://api.github.com/repos/mkjpryor-stfc/my-test-repo
#> __main__.Repository({
#   'id': 261995040,
#   'name': 'test-update-name',
#   'full_name': 'mkjpryor-stfc/test-update-name',
#   'private': False,
#  })
```

However, because resources are lazy-loaded by default, use the fluent API doesn't necessarily mean an
additional HTTP request. In this example, we can see that although we are using the fluent API, the
repository is not actually loaded before the update takes place. This is because we only need the
repository `full_name` to construct the update URL, which we already have:

```python
updated = github.repos.get("mkjpryor-stfc/my-test-repo")._update(name = "test-update-name")
#> API request: PATCH https://api.github.com/repos/mkjpryor-stfc/my-test-repo

print(updated)
#> __main__.Repository({
#   'id': 261995040,
#   'name': 'test-update-name',
#   'full_name': 'mkjpryor-stfc/test-update-name',
#   'private': False,
#  })
```

Similar to updating, deleting a resource can be done either using the resource instance or using
the manager:

```python
# Using an existing repository
repository._delete()

# Using the manager
github.repos.delete("mkjpryor-stfc/my-test-repo")

#> API request: DELETE https://api.github.com/repos/mkjpryor-stfc/my-test-repo
```
