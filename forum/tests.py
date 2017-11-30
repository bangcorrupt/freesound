#
# Freesound is (c) MUSIC TECHNOLOGY GROUP, UNIVERSITAT POMPEU FABRA
#
# Freesound is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# Freesound is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Authors:
#     See AUTHORS file.
#

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from forum.models import Forum, Thread, Post, Subscription


class ForumPostSignalTestCase(TestCase):
    """Tests for the pre/post save signals on Forum, Thread, and Post objects"""

    def setUp(self):
        self.user = User.objects.create_user("testuser", password="testpass", email='email@freesound.org')
        self.forum = Forum.objects.create(name="testForum", name_slug="test_forum", description="test")
        self.thread = Thread.objects.create(forum=self.forum, title="testThread", author=self.user)

    def test_add_unmoderated_post(self):
        """Some users' posts are created unmoderated, this should not update summary values"""

        self.assertEqual(self.thread.num_posts, 0)
        self.assertEqual(self.forum.num_posts, 0)
        post = Post.objects.create(thread=self.thread, author=self.user, body="", moderation_state="NM")

        self.thread.refresh_from_db()
        self.assertEqual(self.thread.num_posts, 0)
        self.forum.refresh_from_db()
        self.assertEqual(self.forum.num_posts, 0)

    def test_add_moderated_post(self):
        """Whitelisted users' posts are automatically moderated OK and immediately available.
        The default moderation state is OK
        """

        self.assertEqual(self.thread.num_posts, 0)
        self.assertEqual(self.forum.num_posts, 0)
        post = Post.objects.create(thread=self.thread, author=self.user, body="")

        self.thread.refresh_from_db()
        self.assertEqual(self.thread.num_posts, 1)
        self.assertEqual(self.thread.last_post, post)
        self.forum.refresh_from_db()
        self.assertEqual(self.forum.num_posts, 1)
        self.assertEqual(self.forum.last_post, post)

    def test_moderate_post(self):
        """A post whose moderation status is changed to OK causes counts to increase"""

        post = Post.objects.create(thread=self.thread, author=self.user, body="", moderation_state="NM")

        self.thread.refresh_from_db()
        # Thread initially has no posts...
        self.assertEqual(self.thread.num_posts, 0)

        post.moderation_state = "OK"
        post.save()

        # But after post moderation it has one
        self.thread.refresh_from_db()
        self.assertEqual(self.thread.num_posts, 1)
        self.assertEqual(self.thread.last_post, post)

    def test_moderate_post_not_lastest(self):
        """When a post is moderated, it might not be the most recent post of a thread or forum"""

        firstpost = Post.objects.create(thread=self.thread, author=self.user, body="", moderation_state="NM")
        secondpost = Post.objects.create(thread=self.thread, author=self.user, body="", moderation_state="OK")

        self.thread.refresh_from_db()
        # Last post of the thread is the most recently created one
        self.assertEqual(self.thread.last_post, secondpost)

        firstpost.moderation_state = "OK"
        firstpost.save()

        # After the first post is moderated, last post of the thread is still the most recent one
        self.thread.refresh_from_db()
        self.assertEqual(self.thread.num_posts, 2)
        self.assertEqual(self.thread.last_post, secondpost)

    def test_remove_moderated_post(self):
        """Removing a moderated post decreses count and might change last_post"""

        firstpost = Post.objects.create(thread=self.thread, author=self.user, body="", moderation_state="OK")
        secondpost = Post.objects.create(thread=self.thread, author=self.user, body="", moderation_state="OK")
        thirdpost = Post.objects.create(thread=self.thread, author=self.user, body="", moderation_state="OK")

        self.thread.refresh_from_db()
        self.assertEqual(self.thread.num_posts, 3)
        self.assertEqual(self.thread.last_post, thirdpost)

        thirdpost.delete()

        self.thread.refresh_from_db()
        self.assertEqual(self.thread.num_posts, 2)
        self.assertEqual(self.thread.last_post, secondpost)

        firstpost.delete()

        self.thread.refresh_from_db()
        self.assertEqual(self.thread.num_posts, 1)
        self.assertEqual(self.thread.last_post, secondpost)

    def test_remove_unmoderated_post(self):
        """Removing an unmoderated post does not decrese count or change last_post"""

        firstpost = Post.objects.create(thread=self.thread, author=self.user, body="", moderation_state="OK")
        secondpost = Post.objects.create(thread=self.thread, author=self.user, body="", moderation_state="NM")

        self.thread.refresh_from_db()
        # Last post of the thread is the moderated one
        self.assertEqual(self.thread.num_posts, 1)
        self.assertEqual(self.thread.last_post, firstpost)

        secondpost.delete()

        # After the unmoderated post is deleted, no values on the thread have changed
        self.thread.refresh_from_db()
        self.assertEqual(self.thread.num_posts, 1)
        self.assertEqual(self.thread.last_post, firstpost)

    def test_remove_last_post_moderated(self):
        """If the last post of a thread is deleted, the thread is removed"""

        post = Post.objects.create(thread=self.thread, author=self.user, body="", moderation_state="OK")

        self.thread.refresh_from_db()
        self.assertEqual(self.thread.num_posts, 1)

        post.delete()

        with self.assertRaises(Thread.DoesNotExist):
            self.thread.refresh_from_db()

    def test_remove_last_post_unmoderated(self):
        """If there is still an unmoderated post on a thread, the thread is not removed"""

        modpost = Post.objects.create(thread=self.thread, author=self.user, body="", moderation_state="OK")
        unmodpost = Post.objects.create(thread=self.thread, author=self.user, body="", moderation_state="NM")

        self.thread.refresh_from_db()
        self.assertEqual(self.thread.num_posts, 1)

        modpost.delete()

        # The thread still exists, but it has no post data
        self.thread.refresh_from_db()
        self.assertEqual(self.thread.num_posts, 0)
        self.assertEqual(self.thread.last_post, None)

    def test_remove_post_last_in_thread_not_in_forum(self):
        """If the last post of a thread is removed, the last post of the forum may be
        from a different thread"""

        otherthread = Thread.objects.create(forum=self.forum, title="Another thread", author=self.user)

        t1post1 = Post.objects.create(thread=self.thread, author=self.user, body="", moderation_state="OK")
        t1post2 = Post.objects.create(thread=self.thread, author=self.user, body="", moderation_state="OK")
        t2post = Post.objects.create(thread=otherthread, author=self.user, body="", moderation_state="OK")

        self.thread.refresh_from_db()
        otherthread.refresh_from_db()
        self.forum.refresh_from_db()

        self.assertEqual(self.thread.last_post, t1post2)
        self.assertEqual(otherthread.last_post, t2post)
        self.assertEqual(self.forum.last_post, t2post)

        t1post2.delete()

        self.thread.refresh_from_db()
        otherthread.refresh_from_db()
        self.forum.refresh_from_db()

        # After deleting t1post2, the last post of thread1 has changed, but not the last post of the forum
        self.assertEqual(self.thread.last_post, t1post1)
        self.assertEqual(self.forum.last_post, t2post)


class ForumThreadSignalTestCase(TestCase):
    """Test signals of the Thread object"""

    def test_add_and_remove_thread(self):
        # Add new Thread and check if signal updates num_threads value

        user = User.objects.create_user("testuser", password="testpass", email='email@freesound.org')
        forum = Forum.objects.create(name="Second Forum", name_slug="second_forum", description="another forum")

        forum.refresh_from_db()
        self.assertEqual(forum.num_threads, 0)
        thread = Thread.objects.create(forum=forum, title="testThread", author=user)
        forum.refresh_from_db()
        self.assertEqual(forum.num_threads, 1)

        thread2 = Thread.objects.create(forum=forum, title="testThread", author=user)
        forum.refresh_from_db()
        self.assertEqual(forum.num_threads, 2)

        # Now remove one thread and check if the values are updated correctly
        thread2.delete()
        forum.refresh_from_db()
        self.assertEqual(forum.num_threads, 1)

        # Now remove the last threads and check if the values are updated correctly
        thread.delete()
        forum.refresh_from_db()
        self.assertEqual(forum.num_threads, 0)


class ForumTestCase(TestCase):

    def test_cant_view_unmoderated_post(self):
        """If a thread only has an unmoderated post, visting the thread with the client results in HTTP404"""

        user = User.objects.create_user("testuser", password="testpass", email='email@freesound.org')
        forum = Forum.objects.create(name="Second Forum", name_slug="second_forum", description="another forum")
        thread = Thread.objects.create(forum=forum, title="testThread", author=user)

        Post.objects.create(thread=thread, author=user, body="", moderation_state="NM")

        res = self.client.get(reverse("forums-thread",
                                      kwargs={"forum_name_slug": forum.name_slug, "thread_id": thread.id}))
        self.assertEqual(res.status_code, 404)


def _create_forums_threads_posts(author, n_forums=1, n_threads=1, n_posts=5):
    for i in range(0, n_forums):
        forum = Forum.objects.create(
            name='Forum %i' % i,
            name_slug='forum_%i' % i,
            description="Description of forum %i" % i
        )
        for j in range(0, n_threads):
            thread = Thread.objects.create(
                author=author,
                title='Thread %i of forum %i' % (j, i),
                forum=forum
            )
            for k in range(0, n_posts):
                post = Post.objects.create(
                    author=author,
                    thread=thread,
                    body='Text of the post %i for thread %i and forum %i' % (k, j, i)
                )
                if k == 0:
                    thread.first_post = post
                    thread.save()


class ForumPageResponses(TestCase):

    def setUp(self):
        self.N_FORUMS = 1
        self.N_THREADS = 1
        self.N_POSTS = 5
        self.user = User.objects.create_user(username='testuser', email='email@example.com', password='12345')
        _create_forums_threads_posts(self.user, self.N_FORUMS, self.N_THREADS, self.N_POSTS)

    def test_forums_response_ok(self):
        resp = self.client.get(reverse('forums-forums'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['forums']), self.N_FORUMS)  # Check that N_FORUMS are passed to context

    def test_forum_response_ok(self):
        forum = Forum.objects.first()
        resp = self.client.get(reverse('forums-forum', args=[forum.name_slug]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['page'].object_list), self.N_THREADS)  # Check N_THREADS in context

    @override_settings(LAST_FORUM_POST_MINIMUM_TIME=0)
    def test_new_thread_response_ok(self):
        forum = Forum.objects.first()

        # Assert non-logged in user is redirected to login page
        resp = self.client.post(reverse('forums-new-thread', args=[forum.name_slug]), data={
            u'body': [u'New thread body (first post)'], u'subscribe': [u'on'], u'title': [u'New thread title']
        })
        self.assertRedirects(resp, '%s?next=%s' % (
            reverse('login'), reverse('forums-new-thread', args=[forum.name_slug])))

        # Assert logged in user can create new thread
        self.client.force_login(self.user)
        resp = self.client.post(reverse('forums-new-thread', args=[forum.name_slug]), data={
            u'body': [u'New thread body (first post)'], u'subscribe': [u'on'], u'title': [u'New thread title']
        })
        post = Post.objects.get(body=u'New thread body (first post)')
        self.assertRedirects(resp, post.get_absolute_url(), target_status_code=302)

    @override_settings(LAST_FORUM_POST_MINIMUM_TIME=0)
    def test_new_thread_title_length(self):
        forum = Forum.objects.first()

        # Assert logged in user fails creating thread
        long_title = 255 * '1'
        self.client.login(username=self.user.username, password='12345')
        resp = self.client.post(reverse('forums-new-thread', args=[forum.name_slug]), data={
            u'body': [u'New thread body (first post)'], u'subscribe': [u'on'], u'title': [long_title]
        })
        self.assertNotEqual(resp.context['form'].errors, None)

    def test_thread_response_ok(self):
        forum = Forum.objects.first()
        thread = forum.thread_set.first()
        resp = self.client.get(reverse('forums-thread', args=[forum.name_slug, thread.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['page'].object_list), self.N_POSTS)  # Check N_POSTS in context

    def test_post_response_ok(self):
        forum = Forum.objects.first()
        thread = forum.thread_set.first()
        post = thread.post_set.first()
        resp = self.client.get(reverse('forums-post', args=[forum.name_slug, thread.id, post.id]))
        redirected_url = post.thread.get_absolute_url() + "?page=%d#post%d" % (1, post.id)
        self.assertRedirects(resp, redirected_url)

    @override_settings(LAST_FORUM_POST_MINIMUM_TIME=0)
    def test_thread_reply_response_ok(self):
        forum = Forum.objects.first()
        thread = forum.thread_set.first()

        # Assert non-logged in user is redirected to login page
        resp = self.client.post(reverse('forums-reply', args=[forum.name_slug, thread.id]), data={
            u'body': [u'Reply post body'], u'subscribe': [u'on'],
        })
        self.assertRedirects(resp, '%s?next=%s' % (
            reverse('login'), reverse('forums-reply', args=[forum.name_slug, thread.id])))

        # Assert logged in user can reply
        self.client.force_login(self.user)
        resp = self.client.post(reverse('forums-reply', args=[forum.name_slug, thread.id]), data={
            u'body': [u'Reply post body'], u'subscribe': [u'on'],
        })
        post = Post.objects.get(body=u'Reply post body')
        self.assertRedirects(resp, post.get_absolute_url(), target_status_code=302)

    @override_settings(LAST_FORUM_POST_MINIMUM_TIME=0)
    def test_thread_reply_quote_post_response_ok(self):
        forum = Forum.objects.first()
        thread = forum.thread_set.first()
        post = thread.post_set.first()

        # Assert non-logged in user is redirected to login page
        resp = self.client.post(reverse('forums-reply-quote', args=[forum.name_slug, thread.id, post.id]), data={
            u'body': [u'Reply post body'], u'subscribe': [u'on'],
        })
        self.assertRedirects(resp, '%s?next=%s' % (
            reverse('login'), reverse('forums-reply-quote', args=[forum.name_slug, thread.id, post.id])))

        # Assert logged in user can reply
        self.client.force_login(self.user)
        resp = self.client.post(reverse('forums-reply-quote', args=[forum.name_slug, thread.id, post.id]), data={
            u'body': [u'Reply post body'], u'subscribe': [u'on'],
        })
        post = Post.objects.get(body=u'Reply post body')
        self.assertRedirects(resp, post.get_absolute_url(), target_status_code=302)

    def test_edit_post_response_ok(self):
        forum = Forum.objects.first()
        thread = forum.thread_set.first()
        post = thread.post_set.first()

        # Assert non-logged in user can't edit post
        resp = self.client.post(reverse('forums-post-edit', args=[post.id]), data={
            u'body': [u'Edited post body']
        })
        self.assertRedirects(resp, '%s?next=%s' % (reverse('login'), reverse('forums-post-edit', args=[post.id])))

        # Assert logged in user which is not author of post can't edit post
        user2 = User.objects.create_user(username='testuser2', email='email2@example.com', password='12345')
        self.client.force_login(user2)
        resp = self.client.post(reverse('forums-post-edit', args=[post.id]), data={
            u'body': [u'Edited post body']
        })
        self.assertEqual(resp.status_code, 404)

        # Assert logged in user can edit post
        self.client.force_login(self.user)
        resp = self.client.post(reverse('forums-post-edit', args=[post.id]), data={
            u'body': [u'Edited post body']
        })
        self.assertRedirects(resp, post.get_absolute_url(), target_status_code=302)
        edited_post = Post.objects.get(id=post.id)
        self.assertEquals(edited_post.body, u'Edited post body')

    def test_delete_post_response_ok(self):
        forum = Forum.objects.first()
        thread = forum.thread_set.first()
        post = thread.post_set.first()

        # Assert non-logged in user can't delete post
        resp = self.client.get(reverse('forums-post-delete', args=[post.id]))
        self.assertRedirects(resp, '%s?next=%s' % (reverse('login'), reverse('forums-post-delete', args=[post.id])))

        # Assert logged in user which is not author of post can't delete post
        user2 = User.objects.create_user(username='testuser2', email='email2@example.com', password='12345')
        self.client.force_login(user2)
        resp = self.client.get(reverse('forums-post-delete', args=[post.id]))
        self.assertEqual(resp.status_code, 404)

        # Assert logged in user can delete post (see delete confirmation page)
        self.client.force_login(self.user)
        resp = self.client.get(reverse('forums-post-delete', args=[post.id]))
        self.assertEquals(resp.status_code, 200)

    def test_delete_post_confirm_response_ok(self):
        forum = Forum.objects.first()
        thread = forum.thread_set.first()
        post = thread.post_set.last()

        # Assert non-logged in user can't delete post
        resp = self.client.get(reverse('forums-post-delete-confirm', args=[post.id]))
        self.assertRedirects(resp, '%s?next=%s' % (reverse('login'), reverse('forums-post-delete-confirm', args=[post.id])))

        # Assert logged in user which is not author of post can't delete post
        user2 = User.objects.create_user(username='testuser2', email='email2@example.com', password='12345')
        self.client.force_login(user2)
        resp = self.client.get(reverse('forums-post-delete-confirm', args=[post.id]))
        self.assertEqual(resp.status_code, 404)

        # Assert logged in user can delete post
        self.client.force_login(self.user)
        resp = self.client.get(reverse('forums-post-delete-confirm', args=[post.id]))
        new_last_post = thread.post_set.last()
        self.assertRedirects(resp, new_last_post.get_absolute_url(), target_status_code=302)
        # TODO: this case only checks the deletion of the last post of a thread. Deleting the first post of a thread
        # TODO: (or the only post if there's only one) raises a 500 error. This should be fixed and test updated.

    def test_user_subscribe_to_thread(self):
        forum = Forum.objects.first()
        thread = forum.thread_set.first()

        # Assert non-logged in user can't subscribe
        resp = self.client.get(reverse('forums-thread-subscribe', args=[forum.name_slug, thread.id]))
        self.assertRedirects(resp, '%s?next=%s' % (reverse('login'), reverse('forums-thread-subscribe', args=[forum.name_slug, thread.id])))

        # Assert logged in user can subscribe
        user2 = User.objects.create_user(username='testuser2', email='email2@example.com', password='12345')
        self.client.force_login(user2)
        resp = self.client.get(reverse('forums-thread-subscribe', args=[forum.name_slug, thread.id]))
        self.assertEqual(resp.status_code, 302)

        self.assertEqual(Subscription.objects.filter(thread=thread, subscriber=user2).count(), 1)

        # Try to create another subscription for the same user and thread, it should not create it
        resp = self.client.get(reverse('forums-thread-subscribe', args=[forum.name_slug, thread.id]))
        self.assertEqual(resp.status_code, 302)

        self.assertEqual(Subscription.objects.filter(thread=thread, subscriber=user2).count(), 1)

        # Assert logged in user can unsubscribe
        resp = self.client.get(reverse('forums-thread-unsubscribe', args=[forum.name_slug, thread.id]))
        self.assertEqual(resp.status_code, 302)

        self.assertEqual(Subscription.objects.filter(thread=thread, subscriber=user2).count(), 0)

    def test_emails_sent_for_subscription_to_thread(self):
        forum = Forum.objects.first()
        thread = forum.thread_set.first()
        post = thread.post_set.first()

        self.client.force_login(self.user)
        resp = self.client.get(reverse('forums-thread-subscribe', args=[forum.name_slug, thread.id]))
        self.assertEqual(Subscription.objects.filter(thread=thread, subscriber=self.user).count(), 1)

        # User creates new post
        user2 = User.objects.create_user(username='testuser2', email='email2@example.com', password='12345')
        self.client.force_login(user2)

        resp = self.client.get(reverse('forums-thread-subscribe', args=[forum.name_slug, thread.id]))
        self.assertEqual(Subscription.objects.filter(thread=thread, subscriber=user2).count(), 1)

        resp = self.client.post(reverse('forums-reply-quote', args=[forum.name_slug, thread.id, post.id]), data={
            u'body': [u'Reply post body'], u'subscribe': [u'on'],
        })
        post = Post.objects.get(body=u'Reply post body')
        self.assertRedirects(resp, post.get_absolute_url(), target_status_code=302)

        # Both users are subscribed but the email is not sent to the user that is sending the post
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "[freesound] topic reply notification - Thread 0 of forum 0")